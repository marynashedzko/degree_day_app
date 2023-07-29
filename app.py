# app.py
import os
import pandas as pd
from flask import Flask, request, redirect, url_for, render_template
from zipfile import ZipFile

app = Flask(__name__)

# Create the "uploads" folder if it doesn't exist
if not os.path.exists("uploads"):
    os.makedirs("uploads")

def process_file(file_path):
    # Read the file as a DataFrame with specified column names and data types
    data = pd.read_csv(file_path, delimiter=';', escapechar='\\', skipinitialspace=True, names=['ID', 'year', 'month', 'day', 'Tmin', 'temp', 'Tmax', 'precipitation'])
    data = data[data['year'] <= 2020]
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
    # Get the uploaded file
    uploaded_file = request.files["zip_file"]

    if uploaded_file.filename == "":
        return "No file selected. Please choose a zip folder to upload."

    if uploaded_file:
        # Save the zip file to the "uploads" folder
        zip_file_path = os.path.join("uploads", uploaded_file.filename)
        uploaded_file.save(zip_file_path)

        # Extract the contents of the zip file to the "uploads" folder
        with ZipFile(zip_file_path, "r") as zip_ref:
            zip_ref.extractall("uploads")

        # Get a list of all text files in the "meteo_data_24" folder
        meteo_folder_path = os.path.join("uploads", "meteo_data_24")
        text_files = [os.path.join(meteo_folder_path, file) for file in os.listdir(meteo_folder_path) if file.endswith('.txt')]

        # Process each file and store data in a dictionary without converting date columns
        meteo = {}
        for file in text_files:
            name = os.path.splitext(os.path.basename(file))[0]
            data = process_file(file)
            meteo[name] = data

        # Convert date columns to datetime format and handle missing values for all dataframes in the dictionary
        for df_name, df in meteo.items():
            convert_to_datetime(df)

        # Print one of the dataframes (e.g., the first one)
        first_dataframe_key = list(meteo.keys())[0]
        print(f"Printing DataFrame ({first_dataframe_key}):")
        print(meteo[first_dataframe_key])
        
        # Print data types of each column in the DataFrame
        print(f"Data Types of DataFrame ({first_dataframe_key}):")
        print(meteo[first_dataframe_key].dtypes)

        return "Files uploaded and extracted successfully."

    return "Failed to upload the file."

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
