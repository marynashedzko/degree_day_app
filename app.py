# app.py
import os
import pandas as pd
from flask import Flask, request, Response, url_for, render_template
from zipfile import ZipFile
import numpy as np
from werkzeug.utils import secure_filename 
import geopandas as gpd

app = Flask(__name__)

# Create the "uploads" folder if it doesn't exist
if not os.path.exists("uploads"):
    os.makedirs("uploads")

def read_meteo_coords(file_path):
    # Read the coordinates of meteostations from the CSV file in the "uploads" folder
    meteo_coords = pd.read_csv(file_path, delimiter=';', skipinitialspace=True, names=['id', 'lat', 'lon'])

    # Convert to a GeoDataFrame
    meteo_coords_gdf = gpd.GeoDataFrame(meteo_coords, geometry=gpd.points_from_xy(meteo_coords['lon'], meteo_coords['lat']), crs="EPSG:4326")

    return meteo_coords_gdf

    #return meteo_coords_gdf
def process_file(file_path):
    # Read the file as a DataFrame with specified column names and data types
    data = pd.read_csv(file_path, delimiter=';', escapechar='\\', skipinitialspace=True, names=['ID', 'year', 'month', 'day', 'Tmin', 'temp', 'Tmax', 'precipitation'])
    return data

def convert_to_datetime(df):
    # Check if 'year', 'month', and 'day' columns exist before converting
    if all(col in df.columns for col in ['year', 'month', 'day']):
        # Convert date columns to datetime format with errors='coerce'
        df['Date'] = pd.to_datetime(df[['year', 'month', 'day']].astype(str).agg('-'.join, axis=1), format='%Y-%m-%d', errors='coerce')
        # Drop rows with missing dates (NaT values)
        #df.dropna(subset=['Date'], inplace=True)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    # Get the uploaded files
    zip_file = request.files["zip_file"]
    coordinates_file = request.files["coordinates_file"]

    # Get user-defined parameters from the form data
    mosquito_life = int(request.form["mosquito_life"])
    threshold = int(request.form["threshold"])
    requiredDD = int(request.form["requiredDD"])
    start_month = int(request.form["start_month"])
    end_month = int(request.form["end_month"])

    if zip_file.filename == "":
        return "No zip file selected. Please choose a zip folder to upload."

    if coordinates_file.filename == "":
        return "No coordinates file selected. Please choose a CSV file containing coordinates to upload."

    if zip_file and zip_file.filename.endswith('.zip') and coordinates_file and coordinates_file.filename.endswith('.csv'):
        # Save the zip file to the "uploads" folder
        zip_file_path = os.path.join("uploads", secure_filename(zip_file.filename))
        zip_file.save(zip_file_path)

        # Save the coordinates file to the "uploads" folder
        coordinates_file_path = os.path.join("uploads", secure_filename(coordinates_file.filename))
        coordinates_file.save(coordinates_file_path)

        # Extract the contents of the zip file to the "uploads" folder
        with ZipFile(zip_file_path, "r") as zip_ref:
            zip_ref.extractall("uploads")

        # Get a list of all text files in the "meteo_data_24" folder
        meteo_folder_path = os.path.join("uploads", "meteo_data_24")
        text_files = [os.path.join(meteo_folder_path, file) for file in os.listdir(meteo_folder_path) if file.endswith('.txt')]

        # Process each file and store data in a dictionary without converting date columns
        meteo = {}
        max_rows = 0
        for file in text_files:
            name = os.path.splitext(os.path.basename(file))[0]
            data = process_file(file)
            meteo[name] = data
            max_rows = max(max_rows, data.shape[0])

        # Convert date columns to datetime format and handle missing values for all dataframes in the dictionary
        for df_name, df in meteo.items():
            convert_to_datetime(df)
        
        meteo_by_day = {}

        # Filter meteorological data to include only stations with maximum number of rows
        for name, data in meteo.items():
            if data.shape[0] == max_rows:
                meteo_by_day[name] = data

        na_detect = {}

        # Find NaN values in temperature column and filter based on month range
        for name, data in meteo_by_day.items():
            na_values = data[data['temp'].isna()]
            na_values = na_values[(na_values['Date'].dt.month > start_month) & (na_values['Date'].dt.month < end_month)]
            if na_values.shape[0] == 0:
                na_detect[name] = na_values

        meteo_by_day = {name: data for name, data in meteo_by_day.items() if name in na_detect}
        names = list(meteo_by_day.keys())

        # Fill NaN values with 0 in meteorological data
        meteo_by_day = {name: data.fillna(0) for name, data in meteo_by_day.items()}

        # Calculate HDU values
        meteo_by_day = {name: data.assign(HDU=lambda x: x['temp'].apply(lambda temp: max(temp - threshold, 0))) for name, data in meteo_by_day.items()}

        def sumHDU(sq):
            data = meteo_by_day[sq]
            data['HDUsum'] = data['HDU'].rolling(window=mosquito_life).apply(lambda x: 0 if np.sum(x==0) > 4 else np.sum(x), raw=True)
            return data

        HDU_by_day = {}

        # Calculate HDU sum and filter based on requiredDD
        for sq in meteo_by_day:
            HDU_by_day[sq] = sumHDU(sq)


        HDU_by_day = {name: df[df['HDUsum'] > requiredDD] for name, df in HDU_by_day.items()}

        Dates_stfn = {}

        # Group data by year and calculate FirstDay, LastDay, and ID mean
        for name, df in HDU_by_day.items():
            group_by_year = df.groupby(df['Date'].dt.year)
            Dates_stfn[name] = group_by_year.agg(FirstDay=('Date', 'min'), LastDay=('Date', 'max'), id=('ID', 'mean'))

        # Iterate through the first dictionary
        for key, df in Dates_stfn.items():
            second_df = HDU_by_day.get(key)
            
            # Check if the dataframe exists in the second dictionary
            if second_df is not None:
                # Group by year and calculate the sum of 'HDUs'
                summed_hdu = second_df.groupby('year')['HDU'].sum()
                
                # Merge the summed HDUs to the original dataframe
                df = pd.merge(df, summed_hdu, left_on=df['FirstDay'].dt.year, right_index=True, how='left')
                
                # Update the dataframe in the first dictionary
                Dates_stfn[key] = df

        generations = {}
        # Read the meteostation coordinates and convert to GeoDataFrame
        meteo_coords = read_meteo_coords(coordinates_file_path)

        # Calculate gens and create generations dictionary
        for name, df in Dates_stfn.items():
            generations[name] = df.assign(gens=df['HDU'] / requiredDD)[['FirstDay', 'LastDay', 'id', 'HDU', 'gens']]

        gens_bind = pd.concat(generations.values())
        # Extract the year from 'FirstDay' and add it as a new column 'year'
        gens_bind['year'] = gens_bind['FirstDay'].dt.year

        # Convert 'id' to integer type, handle non-finite values by dropping them
        meteo_coords['id'] = pd.to_numeric(meteo_coords['id'], errors='coerce')

        # Drop rows with non-finite 'id' values
        meteo_coords = meteo_coords.dropna(subset=['id'])

        # Merge gens_bind with meteo_coords on 'id'
        gens_bind = pd.merge(gens_bind, meteo_coords, on='id')

        #gens_bind['year'] = pd.to_datetime(gens_bind['FirstDay']).dt.year
        #gens_bind = pd.merge(gens_bind, meteo_coords, on='id')

        groups = gens_bind.groupby('year')
        gens_by_year = {}

        # Group generations data by year
        for year, group in groups:
            gens_by_year[year] = group

        
        #meteo_by_day['22854'].to_csv('22854_meteo_item.csv', index=False)
        #Dates_stfn['22854'].to_csv('22854_dates_item.csv', index=False)
        #generations['22854'].to_csv('22854_generations_item.csv', index=False)
        ##gens_bind.to_csv('gens_bind.csv', index=False)
        #meteo_coords.to_csv('METCOORDS.csv', index = False)
        #gens_by_year[2017].to_csv('gby.csv', index = False)
                

        return "Files uploaded and extracted successfully."

    return "Failed to upload the file."





if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
