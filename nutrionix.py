import requests
import argparse
import spacy
import re
import sys
from collections import defaultdict

#spacy MD model
nlp = spacy.load("en_core_web_sm")
API_KEY = "2a194321937c718c388559f8389cfa9c"
APP_ID = "d2258d05"
BASE_URL = "https://trackapi.nutritionix.com/v2/natural/nutrients"
HEADERS = {
    "x-app-id": APP_ID,
    "x-app-key": API_KEY,
    "Content-Type": "application/json"
}

def parse(text):
    doc = nlp(text)
    
    #anything else?
    units = ["one", "gram", "grams", "g", "ounce", "ounces", "oz", "pound", "pounds", "lb", "lbs", 
             "cup", "cups", "tbsp", "tablespoon", "tablespoons", "tsp", "teaspoon", "teaspoons"]

    num_tokens = [token for token in doc if token.like_num]
    food_items = []
    
    for num_token in num_tokens:
        unit = None
        unit_token = None
        for i in range(1, 4): #parse through next tokens looking for a unit, as long as the sentence is formed normally this should work
            if num_token.i + i < len(doc):
                next_token = doc[num_token.i + i]
                if next_token.text.lower() in units:
                    unit = next_token.text.lower()
                    unit_token = next_token
                    break
    
        if unit:
            food_text = ""
            food_start_idx = unit_token.i + 1
            
            # Skip words like of or the
            while food_start_idx < len(doc) and doc[food_start_idx].is_stop:
                food_start_idx += 1
            
            # Extract the food item - take the noun chunk or the next few tokens
            for chunk in doc.noun_chunks:
                if chunk.start >= food_start_idx and not chunk.text.lower().startswith(tuple(units)):
                    food_text = chunk.text
                    break
            
            # If no noun  was found, just take the next token
            if not food_text and food_start_idx < len(doc):  food_text = doc[food_start_idx].text
      
            if food_text:  food_items.append((num_token.text, unit, food_text))
    
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
            food_info = {
                "food_name": food['food_name'],
                "quantity": f"{food['serving_qty']} {food['serving_unit']}",
                "calories": food['nf_calories'],
                "protein": food['nf_protein'],
                "carbs": food['nf_total_carbohydrate'],
                "fat": food['nf_total_fat'],
                "sugar": food['nf_sugars']
            }
            
            if food['nf_calories']: total_macros["calories"] += food['nf_calories']
            if food['nf_protein']: total_macros["protein"] += food['nf_protein']
            if food['nf_total_carbohydrate']: total_macros["carbs"] += food['nf_total_carbohydrate']
            if food['nf_total_fat']: total_macros["fat"] += food['nf_total_fat']
            if food['nf_sugars']: total_macros["sugar"] += food['nf_sugars']
            
            results.append(food_info)
        
        return results, total_macros
    else:
        print(f"Error: {response.status_code}, {response.text}")
        return None, None

def results(food_results, total_macros):
    print("Food Diary \n")

    
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
    print("=" * 50)

def main():
    parser = argparse.ArgumentParser(description="Track food intake and calculate macros to calculate insulin dose")
    parser.add_argument('text', nargs='+', help="Your food diary entry (e.g., 'I ate 100 grams of rice')")
    
    args = parser.parse_args()
    food_entry = " ".join(args.text)
    food_items = parse(food_entry)
    
    if not food_items:
        print("No food items with quantities were detected. Please try again with a more specific entry.")
        sys.exit(1)
    food_results, total_macros = getmacros(food_items)
    
    if food_results:
        results(food_results, total_macros)
    else:
        print("Could not retrieve nutrition information. Please check your input and try again.")

if __name__ == "__main__":
    main()