import requests
import argparse
import spacy
import re
import sys
import pandas as pd
import numpy as np
import datetime
from collections import defaultdict

nlp = spacy.load("en_core_web_sm")
API_KEY = "2a194321937c718c388559f8389cfa9c"
APP_ID = "d2258d05"
BASE_URL = "https://trackapi.nutritionix.com/v2/natural/nutrients"
HEADERS = {
    "x-app-id": APP_ID,
    "x-app-key": API_KEY,
    "Content-Type": "application/json"
}

time_sensitivity_factors = {}
MAXBOLUS = 10

def parse(text):
    doc = nlp(text)
    units = ["one", "gram", "grams", "g", "ounce", "ounces", "oz", "pound", "pounds", "lb", "lbs", 
             "cup", "cups", "tbsp", "tablespoon", "tablespoons", "tsp", "teaspoon", "teaspoons"]

    num_tokens = [token for token in doc if token.like_num]
    food_items = []
    for num_token in num_tokens:
        unit = None
        unit_token = None
        for i in range(1, 4): # parse through next tokens looking for a m unit
            if num_token.i + i < len(doc):
                next_token = doc[num_token.i + i]
                if next_token.text.lower() in units:
                    unit = next_token.text.lower()
                    unit_token = next_token
                    break
        if unit:
            food_text = ""
            st_id = unit_token.i + 1
            while st_id < len(doc) and doc[st_id].is_stop:
                st_id += 1
          
            for chunk in doc.noun_chunks:#NOT FOOD SPECIFIC
                if chunk.start >= st_id and not chunk.text.lower().startswith(tuple(units)):
                    food_text = chunk.text
                    break
            if not food_text and st_id < len(doc):  
                food_text = doc[st_id].text
            if food_text:  
                food_items.append((num_token.text, unit, food_text))
    return food_items

def getmacros(food_items):
    
    query_parts = []
    for quantity, unit, food in food_items:
        query_parts.append(f"{quantity} {unit} of {food}") 
    query = " and ".join(query_parts)
    data = {"query": query}
    response = requests.post(BASE_URL, json=data, headers=HEADERS)
    
    if response.status_code == 200:
        food_data = response.json()
        results = []
        total_macros = defaultdict(float)
        
        for food in food_data['foods']:
            #print(type(food)
            food_info = {"food_name": food['food_name'], "quantity": f"{food['serving_qty']} {food['serving_unit']}","calories": food['nf_calories'],"protein": food['nf_protein'],"carbs": food['nf_total_carbohydrate'],"fat": food['nf_total_fat'],"sugar": food['nf_sugars']}  
            if food['nf_calories']: total_macros["calories"] += food['nf_calories']
            if food['nf_protein']: total_macros["protein"] += food['nf_protein']
            if food['nf_total_carbohydrate']: total_macros["carbs"] += food['nf_total_carbohydrate']
            if food['nf_total_fat']: total_macros["fat"] += food['nf_total_fat']
            if food['nf_sugars']: total_macros["sugar"] += food['nf_sugars'] 
            results.append(food_info)
        
        return results, total_macros

def load(file_path): #MUST BE IN DEXCOM FORM, AND FIRST 20 COLUMNS ISH DELETED
    df = pd.read_csv(file_path)
    data = df[['Timestamp', 'Glucose Value (mg/dL)']]
    data['Timestamp'] = pd.to_datetime(data['Timestamp'])
    data['Glucose Value (mg/dL)'] = pd.to_numeric(data['Glucose Value (mg/dL)'], errors='coerce')
    data = data.dropna(subset=['Glucose Value (mg/dL)'])
    return data
    
def factor(glucose_data):
    #loc?
    glucose_data['Glucose Value (mg/dL)'] = pd.to_numeric(glucose_data['Glucose Value (mg/dL)'], errors='coerce')
    glucose_data = glucose_data.dropna(subset=['Glucose Value (mg/dL)'])
    glucose_data['hour'] = glucose_data['Timestamp'].dt.hour
    
    hourly_stats = glucose_data.groupby('hour')['Glucose Value (mg/dL)'].agg(['mean', 'std', 'min', 'max', 'count'])
    global time_sensitivity_factors#tbf
    overall_mean = glucose_data['Glucose Value (mg/dL)'].mean()
    
    morning = glucose_data[(glucose_data['hour'] >= 8) & (glucose_data['hour'] < 12)]['Glucose Value (mg/dL)'].mean()
    afternoon = glucose_data[(glucose_data['hour'] >= 12) & (glucose_data['hour'] < 18)]['Glucose Value (mg/dL)'].mean()
    evening = glucose_data[(glucose_data['hour'] >= 18) & (glucose_data['hour'] < 22)]['Glucose Value (mg/dL)'].mean()
    night = glucose_data[(glucose_data['hour'] >= 22) | (glucose_data['hour'] < 8)]['Glucose Value (mg/dL)'].mean()
    
    highest_avg = max(morning, afternoon, evening, night)
    lowest_avg = min(morning, afternoon, evening, night)
    
    for hour, stats in hourly_stats.iterrows():
        if stats['count'] >= 10 and not np.isnan(stats['mean']):  
            relative_value = stats['mean'] / overall_mean
            sensitivity = 2 - relative_value  
            sensitivity = max((lowest_avg/highest_avg), min((highest_avg/lowest_avg), sensitivity))
            time_sensitivity_factors[hour] = sensitivity
        else:
            time_sensitivity_factors[hour] = 1.0

    
    print(f"Morning average (8am-12pm): {morning:.1f} mg/dL")
    print(f"Afternoon average (12pm-6pm): {afternoon:.1f} mg/dL")
    print(f"Evening average (6pm-10pm): {evening:.1f} mg/dL")
    print(f"Night average (10pm-8am): {night:.1f} mg/dL")
    
    return time_sensitivity_factors

def getsns(current_time):
   
    hour = current_time.hour
    if hour in time_sensitivity_factors:
        return time_sensitivity_factors[hour]
    return 1.0

def calculate_bolus(carbs, blood_glucose=None, target_bg=100, icr=15, cf=50, iob=0, current_time=None, model=None, previous_readings=[]):
   
    if current_time is None:
        current_time = datetime.datetime.now()
    tbf = getsns(current_time)
    #time_factor = .8
    #print(time_factor)
    adjusted_icr = icr * tbf  
    adjusted_cf = cf * tbf   
    carb_bolus = carbs / adjusted_icr

    correction_bolus = 0
    if blood_glucose is not None and blood_glucose > target_bg:
        correction_bolus = (blood_glucose - target_bg) / adjusted_cf
    

    raw_bolus = carb_bolus + correction_bolus - iob
    final_bolus = max(0, round(raw_bolus, 1))
    if final_bolus > MAXBOLUS:
        print("Max Bolus is above 10 units, please ensure the meal is correctly inputted")
        final_bolus = MAXBOLUS
    
    return final_bolus

def results(food_results, total_macros, blood_glucose=None, target_bg=100, icr=15, cf=50, 
           iob=0, current_time=None, model=None, previous_readings=[]):
    print("Meal contents: \n")
    for food in food_results:
        if food['food_name'] is not None: print(f"Food: {food['food_name']}") 
        else: print('N/a')
        if food['quantity'] is not None:print(f"Quantity: {food['quantity']}")
        else: print("N/a")
        if food['calories'] is not None:print(f"Calories: {food['calories']:.1f} kcal")
        else: print("calories: 0.0g")
        if food['protein'] is not None:print(f"Protein: {food['protein']:.1f} g")
        else: print("protein: 0.0g")
        if food['carbs'] is not None:print(f"Carbs: {food['carbs']:.1f} g")
        else: print("carbs: 0.0g")
        if food['fat'] is not None:print(f"Fat: {food['fat']:.1f} g")
        else: print("fat: 0.0g")
        if food['sugar'] is not None: print(f"Sugar: {food['sugar']:.1f} g")
        else: print("sugar: 0.0g")
       
    print("\nTOTAL MACROS:")
    print(f"Calories: {total_macros['calories']:.1f} kcal")
    print(f"Protein: {total_macros['protein']:.1f} g")
    print(f"Carbs: {total_macros['carbs']:.1f} g")
    print(f"Fat: {total_macros['fat']:.1f} g")
    print(f"Sugar: {total_macros['sugar']:.1f} g")
    
    bolus = calculate_bolus(carbs=total_macros['carbs'],blood_glucose=blood_glucose,target_bg=target_bg, icr=icr, cf=cf,iob=iob,current_time=current_time)
    print(f"Recommended bolus: {bolus} units")

    if blood_glucose is None:
        print("\nNote: This is based only on carbs. No blood glucose provided for correction.")
   
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('text', nargs='+', help="Your food diary entry (e.g., 'I ate 100 grams of rice')")
    parser.add_argument('--bg', type=float)
    parser.add_argument('--target', type=float, default=100)
    parser.add_argument('--icr', type=float, default=15)
    parser.add_argument('--cf', type=float, default=50)
    parser.add_argument('--iob', type=float, default=0)
    parser.add_argument('--cgm-data', type=str, help="Path to CGM data CSV file")
   
    args = parser.parse_args()
    glucose_data = None
    
    if args.cgm_data:
        try:
            glucose_data = load(args.cgm_data)
            if glucose_data is not None and not glucose_data.empty:
                factors = factor(glucose_data)
            else:
                print("Default calculations")
        except Exception as e:
            print(f"error:{e}")

    current_time = datetime.datetime.now()
    previous_readings = []
    if glucose_data is not None and not glucose_data.empty:
        previous_data = glucose_data[glucose_data['Timestamp'] < pd.Timestamp(current_time)]
        previous_data = previous_data.sort_values('Timestamp', ascending=False).head(3)
        previous_readings = previous_data['Glucose Value (mg/dL)'].tolist()
 
    food_entry = " ".join(args.text)
    food_items = parse(food_entry)
    
    if not food_items:
        print("No food items/quantities were not detected")
        sys.exit(1)
    try:
        food_results, total_macros = getmacros(food_items)    
        if food_results:
            results(food_results, total_macros, 
                    blood_glucose=args.bg, 
                    target_bg=args.target,
                    icr=args.icr, 
                    cf=args.cf, 
                    iob=args.iob,
                    current_time=current_time,
                    previous_readings=previous_readings)
        else:
            print("Could not retrieve nutrition information")
    except Exception as e:
        print(f"Error calculating results: {e}")
       
if __name__ == "__main__":
    main()