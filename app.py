import io
import zipfile
import os
import pandas as pd
from flask import Flask, request, render_template, send_file
from zipfile import ZipFile
import numpy as np
from werkzeug.utils import secure_filename
import geopandas as gpd

app = Flask(__name__)

# Create the "uploads" folder if it doesn't exist
if not os.path.exists("uploads"):
    os.makedirs("uploads")

# Read meteostation coordinates from a CSV file and convert to GeoDataFrame
def read_meteo_coords(file_path):
    meteo_coords = pd.read_csv(file_path, delimiter=';', skipinitialspace=True, names=['id', 'lat', 'lon'])
    meteo_coords_gdf = gpd.GeoDataFrame(meteo_coords, geometry=gpd.points_from_xy(meteo_coords['lon'], meteo_coords['lat']), crs="EPSG:4326")
    return meteo_coords_gdf

# Process a file to create a DataFrame with specific column names and data types
def process_file(file_path):
    data = pd.read_csv(file_path, delimiter=';', escapechar='\\', skipinitialspace=True, names=['ID', 'year', 'month', 'day', 'Tmin', 'temp', 'Tmax', 'precipitation'])
    return data

# Convert 'year', 'month', and 'day' columns to datetime format
def convert_to_datetime(df):
    if all(col in df.columns for col in ['year', 'month', 'day']):
        df['Date'] = pd.to_datetime(df[['year', 'month', 'day']].astype(str).agg('-'.join, axis=1), format='%Y-%m-%d', errors='coerce')

@app.route("/download_zip", methods=["GET"])
def download_zip():
    global gens_by_year
    
    # Check if there is data available in the 'gens_by_year' dictionary
    if gens_by_year:
        # Create an in-memory zip file
        zip_buffer = io.BytesIO()

        # Create a ZipFile object and add CSV files for each year's data
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for year, df in gens_by_year.items():
                # Convert DataFrame to CSV data
                csv_data = df.to_csv(index=False)
                # Define the file name for the CSV in the zip file
                file_name = f'gens_by_year_{year}.csv'
                # Write CSV data to the zip file
                zipf.writestr(file_name, csv_data)

        # Move the buffer position to the beginning
        zip_buffer.seek(0)

        # Return the zip file as a downloadable attachment
        return send_file(
            zip_buffer,
            download_name='gens_by_year.zip',
            as_attachment=True,
            mimetype='application/zip'
        )
    else:
        # Return a message if no data is available for download
        return "No data available to download."

# Route to render the index page
@app.route("/")
def index():
    return render_template("index.html")

# Dictionary to store computed data by year
gens_by_year = {}

# Route to handle file upload and data processing
@app.route("/upload", methods=["POST"])
def upload():
    zip_file = request.files["zip_file"]
    coordinates_file = request.files["coordinates_file"]
    mosquito_life = int(request.form["mosquito_life"])
    threshold = int(request.form["threshold"])
    requiredDD = int(request.form["requiredDD"])
    start_month = int(request.form["start_month"])
    end_month = int(request.form["end_month"])

    # Check if the selected files are valid
    if not zip_file.filename or not zip_file.filename.endswith('.zip') or not coordinates_file.filename or not coordinates_file.filename.endswith('.csv'):
        return "Invalid files selected. Please choose a zip folder and a CSV file."

    # Save uploaded files
    zip_file_path = os.path.join("uploads", secure_filename(zip_file.filename))
    zip_file.save(zip_file_path)
    coordinates_file_path = os.path.join("uploads", secure_filename(coordinates_file.filename))
    coordinates_file.save(coordinates_file_path)

    # Extract contents from the zip file
    with ZipFile(zip_file_path, "r") as zip_ref:
        zip_ref.extractall("uploads")

    meteo_folder_path = os.path.join("uploads", "meteo_data_24")
    text_files = [os.path.join(meteo_folder_path, file) for file in os.listdir(meteo_folder_path) if file.endswith('.txt')]

    # Process and filter meteorological data
    meteo = {}
    max_rows = 0
    for file in text_files:
        name = os.path.splitext(os.path.basename(file))[0]
        data = process_file(file)
        meteo[name] = data
        max_rows = max(max_rows, data.shape[0])

    for df_name, df in meteo.items():
        convert_to_datetime(df)
    
    # Dictionary to store meteorological data for each day
    meteo_by_day = {}

    complete_stations = []
    incomplete_stations = []

    # Filter meteorological data for complete datasets and store them in 'meteo_by_day' dictionary
    for name, data in meteo.items():
        if data.shape[0] == max_rows:
            complete_stations.append(name)
            meteo_by_day[name] = data
        else:
            incomplete_stations.append(name)

    # handle missing values
    na_detect = {}
    for name, data in meteo_by_day.items():
        na_values = data[data['temp'].isna()]
        na_values = na_values[(na_values['Date'].dt.month > start_month) & (na_values['Date'].dt.month < end_month)]
        if na_values.shape[0] == 0:
            na_detect[name] = na_values

    # Filter 'meteo_by_day' data for stations with no missing values and store them in 'meteo_by_day' again
    meteo_by_day = {name: data for name, data in meteo_by_day.items() if name in na_detect}

    # Get the list of station names
    names = list(meteo_by_day.keys())

    # Fill missing temperature values with 0 in 'meteo_by_day' data
    meteo_by_day = {name: data.fillna(0) for name, data in meteo_by_day.items()}

    # Calculate the Heat Degree Unit (HDU) for each station's temperature data
    meteo_by_day = {name: data.assign(HDU=lambda x: x['temp'].apply(lambda temp: max(temp - threshold, 0))) for name, data in meteo_by_day.items()}

    def sumHDU(sq):
        # Calculate the rolling sum of HDU values for the given station's data
        data = meteo_by_day[sq]
        data['HDUsum'] = data['HDU'].rolling(window=mosquito_life).apply(lambda x: 0 if np.sum(x==0) > 4 else np.sum(x), raw=True)
        return data


    # Calculate HDU values for each meteorological station and process the data
    HDU_by_day = {}  # Dictionary to store HDU values for each station
    for sq in meteo_by_day:
        HDU_by_day[sq] = sumHDU(sq)  # Calculate HDUsum values using sumHDU function

    # Filter stations based on requiredDD and group data by year for further processing
    HDU_by_day = {name: df[df['HDUsum'] > requiredDD] for name, df in HDU_by_day.items()}
    Dates_stfn = {}  # Dictionary to store processed data for each station

    # Group filtered HDU data by year and compute required metrics
    for name, df in HDU_by_day.items():
        group_by_year = df.groupby(df['Date'].dt.year)
        Dates_stfn[name] = group_by_year.agg(FirstDay=('Date', 'min'), LastDay=('Date', 'max'), id=('ID', 'mean'))

    # Process the grouped data to calculate aggregated HDU values
    for key, df in Dates_stfn.items():
        second_df = HDU_by_day.get(key)
        if second_df is not None:
            summed_hdu = second_df.groupby('year')['HDU'].sum()
            df = pd.merge(df, summed_hdu, left_on=df['FirstDay'].dt.year, right_index=True, how='left')
            Dates_stfn[key] = df

    # Calculate the number of generations and create the 'generations' dictionary
    generations = {}
    meteo_coords = read_meteo_coords(coordinates_file_path)

    # Compute the number of generations using calculated HDU values
    for name, df in Dates_stfn.items():
        generations[name] = df.assign(gens=df['HDU'] / requiredDD)[['FirstDay', 'LastDay', 'id', 'HDU', 'gens']]

    # Concatenate all station data to form 'gens_bind' DataFrame
    gens_bind = pd.concat(generations.values())
    gens_bind['year'] = gens_bind['FirstDay'].dt.year

    # Convert 'id' column to numeric type and drop rows with non-finite 'id' values
    meteo_coords['id'] = pd.to_numeric(meteo_coords['id'], errors='coerce')
    meteo_coords = meteo_coords.dropna(subset=['id'])

    # Merge 'gens_bind' DataFrame with 'meteo_coords' on 'id' column
    gens_bind = pd.merge(gens_bind, meteo_coords, on='id')


    # Merge data and group by year for 'gens_by_year' dictionary
    groups = gens_bind.groupby('year')
    global gens_by_year
    gens_by_year = {}
    for year, group in groups:
        gens_by_year[year] = group

    # Render the template with the download link
    return render_template("download_link.html")

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
