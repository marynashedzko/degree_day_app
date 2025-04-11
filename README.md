# degree_day_app

## User Guide

### Data Requirements
The program processes meteorological station data, filtering out datasets with missing values and using only complete datasets for analysis.

### Analysis
The core functionality of the application is based on the degree day method, adapted from Genchi et al. (2005). The algorithm involves the following steps:

1. **Calculation of Degree Days (Heating Degree Units - HDUs)**  
    - HDUs are calculated by subtracting the user-defined temperature threshold from each mean temperature value.  
    - If the mean temperature is lower than or equal to the threshold, the HDU value is set to zero, as negative values are not relevant for the analysis.

2. **Cumulative HDU Calculation**  
    - To account for vector lifespan, the application uses a rolling sum method.  
    - HDUs are summed over a user-defined rolling window corresponding to the vector's lifespan.  
    - The algorithm allows up to 3 consecutive days with HDU values of zero to account for temporary temperature drops that do not affect pathogen development.  
    - Example function for this step:
      ```python
      def sumHDU(sq):
            data = meteo_by_day[sq]
            data['HDUsum'] = data['HDU'].rolling(window=mosquito_life).apply(
                 lambda x: 0 if np.sum(x == 0) > 3 else np.sum(x), raw=True
            )
            return data
      ```

3. **Transmission Season Dates**  
    - The start date is identified as the first day when cumulative HDU reaches the required value within the vector's lifespan.  
    - The end date is the last day after the start when the cumulative HDU value meets the requirement.

4. **Number of Generations**  
    - The algorithm calculates the possible number of pathogen generations by dividing cumulative HDUs (between the start and end dates) by the required cumulative HDUs.

5. **Output**  
    - The algorithm outputs a dictionary containing processed data by year. Each dictionary entry corresponds to a year and includes a DataFrame with the following columns:  
      - **FirstDay**: First day of the transmission season  
      - **LastDay**: Last day of the transmission season  
      - **id**: Meteorological station identifier  
      - **HDU**: Cumulative Heating Degree Units over the transmission period  
      - **gens**: Number of pathogen generations  
      - **year**: Year associated with the data  
      - **lat**: Latitude of the station's location  
      - **long**: Longitude of the station's location  
      - **geometry**: Geopandas column storing spatial information (geographical coordinates of the station)

## Input Guide

### Input Data

#### Meteorological Station Data
Provide a `.zip` file containing `.txt` files with meteorological data for each station. Each file should be named using the meteorological station ID and formatted as follows:
```
22003;1997; 5; 1; -3.4;  1.2;  3.5;  0.0
22003;1997; 5; 2;  1.6;  2.8;  4.3;  1.6
22003;1997; 5; 3;  0.3;  1.6;  2.2;  0.3
22003;1997; 5; 4;  0.9;  1.3;  1.7;  1.3
22003;1997; 5; 5; -0.1;  0.8;  1.8;  2.6
22003;1997; 5; 6;  0.0;  1.6;  3.2;  0.8
22003;1997; 5; 7;  0.2;  2.6;  5.5;  0.0
22003;1997; 5; 8;  0.0;  0.8;  1.4;  0.0
22003;1997; 5; 9; -1.2;  3.2;  6.1;  0.0
```
Refer to the `Data` folder for an example. To minimize errors, ensure the `.zip` file and its internal folder are named `meteo_data_24`. (I don't remember if different naming can cause issues).

NOTE: This is the data, retrieved from http://aisori-m.meteo.ru/waisori/ and follows their format

#### Meteorological Station Coordinates
Provide a `.csv` file containing the spatial coordinates (latitude and longitude) of the meteorological stations. The file should include the station ID and be formatted as follows:
```
25173;68.9;-179.6333333
25378;66.35;-179.1166667
25372;67.16666667;-178.9333333
25282;67.83333333;-175.8333333
25594;64.38333333;-173.2333333
25399;66.16666667;-169.8333333
23986;60.38333333;93.33333333
29594;55.95;98
24817;61.26666667;108.1666667
24967;60.46666667;130
20107;78.66666667;14.25
25954;60.35;166
26701;54.65;19.88333333
26702;54.7;20.61666667
26706;54.36666667;21.3
26614;55.08;21.93333333
22907;60.83333333;26.98333333
26157;58.73333333;27.83333333
26258;57.81666667;28.33333333
```
Ensure the file includes accurate station IDs and coordinates for proper spatial analysis.

### Vector Lifespan
- **Description**: The number of days the vector (e.g., mosquito) typically lives.
- **Example**: 30 for mosquitoes.

### Temperature Threshold
- **Description**: Minimum daily mean temperature for pathogen development.
- **Example**: 14 °C for heartworm.

### Required Degree Days
- **Description**: Total degree-days needed for pathogen to develop.
- **Example**: 130 for heartworm.

### Start Month
- **Description**: Presumed beginning of transmission season (1–12).
- **Example**: 5 for May.

### End Month
- **Description**: Presumed end of transmission season (1–12).
- **Example**: 9 for September.

**NOTE:** The start and end months are used to make calculations more efficient and precise by narrowing the time frame for analysis.
If you are unsure about the transmission season, use January (1) as the start month and December (12) as the end month to cover the entire year.
