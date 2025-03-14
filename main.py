import spacy
from spacy.matcher import Matcher, PhraseMatcher
import re

# Load spaCy model
nlp = spacy.load("en_core_web_sm")

# Define a more comprehensive food extraction function
def extract_food_info(text):
    doc = nlp(text)
    
    # Create matchers
    matcher = Matcher(nlp.vocab)
    phrase_matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
    
    # Define units with normalization factors (to grams or ml)
    # This will help with macro calculations later
    units = {
        # Weight units
        "g": 1,
        "gram": 1,
        "grams": 1,
        "kg": 1000,
        "kilogram": 1000,
        "kilograms": 1000,
        "mg": 0.001,
        "milligram": 0.001,
        "milligrams": 0.001,
        # Volume units
        "cup": 240,  # ~240g/ml for water-based foods
        "cups": 240,
        "oz": 28.35,
        "ounce": 28.35,
        "ounces": 28.35,
        "tbsp": 15,
        "tablespoon": 15,
        "tablespoons": 15,
        "tsp": 5,
        "teaspoon": 5,
        "teaspoons": 5,
        "ml": 1,
        "milliliter": 1,
        "milliliters": 1,
        "l": 1000,
        "liter": 1000,
        "liters": 1000,
        # Count units
        "piece": 1,
        "pieces": 1,
        "slice": 1,
        "slices": 1,
        # Default
        "unit": 1,
        "units": 1
    }
    
    # Common food adjectives to include
    food_adjectives = ["whole", "skim", "low-fat", "nonfat", "organic", "fresh", "frozen", 
                      "canned", "dried", "raw", "cooked", "boiled", "fried", "baked", "grilled", 
                      "steamed", "roasted"]
    
    # Add food adjectives to the phrase matcher
    adjective_patterns = [nlp(adj) for adj in food_adjectives]
    phrase_matcher.add("FOOD_ADJ", adjective_patterns)
    
    # More comprehensive patterns
    # Pattern 1: Number → Unit → (Adjective) → Food (e.g., "2 cups of white rice")
    pattern1 = [
        {"LIKE_NUM": True},
        {"LOWER": {"IN": list(units.keys())}},
        {"LOWER": {"IN": ["of", ""]}, "OP": "?"},
        {"POS": "ADJ", "OP": "*"},  # Optional adjectives
        {"POS": "NOUN"}
    ]
    
    # Pattern 2: Number → (Adjective) → Food (e.g., "2 apples")
    pattern2 = [
        {"LIKE_NUM": True},
        {"POS": "ADJ", "OP": "*"},  # Optional adjectives
        {"POS": "NOUN"}
    ]
    
    # Pattern 3: Catch compound foods (e.g., "peanut butter")
    pattern3 = [
        {"LIKE_NUM": True},
        {"LOWER": {"IN": list(units.keys())}},
        {"LOWER": {"IN": ["of", ""]}, "OP": "?"},
        {"POS": "NOUN"},
        {"POS": "NOUN"}
    ]
    
    # Add patterns to matcher
    matcher.add("QUANTITY_UNIT_FOOD", [pattern1, pattern2, pattern3])
    
    # Find matches
    matches = matcher(doc)
    ingredients = []
    
    for match_id, start, end in matches:
        span = doc[start:end]
        span_text = span.text
        
        # Extract quantity using regex for complex numbers (like "1/2", "1.5")
        quantity_match = re.search(r'(\d+\/\d+|\d+\.\d+|\d+)', span_text)
        if quantity_match:
            quantity_str = quantity_match.group(1)
            # Convert fractions to decimal
            if '/' in quantity_str:
                num, denom = quantity_str.split('/')
                quantity = float(num) / float(denom)
            else:
                quantity = float(quantity_str)
        else:
            quantity = 1.0  # Default
        
        # Extract unit
        unit_found = False
        for unit in units.keys():
            if re.search(r'\b' + unit + r'\b', span_text.lower()):
                unit_found = True
                normalization_factor = units[unit]
                break
        
        if not unit_found:
            unit = "unit"
            normalization_factor = 1
        
        # Extract food by removing quantity and unit from the span
        food_text = re.sub(r'^\d+\/\d+|\d+\.\d+|\d+', '', span_text).strip()
        food_text = re.sub(r'\b' + unit + r'\b', '', food_text, flags=re.IGNORECASE).strip()
        food_text = re.sub(r'^of\s+', '', food_text).strip()  # Remove "of" if present
        
        # Only add if we have a valid food item (not just numbers or units)
        if food_text and not all(token.is_stop for token in nlp(food_text)):
            ingredients.append({
                "quantity": quantity,
                "unit": unit,
                "unit_factor": normalization_factor,
                "normalized_quantity": quantity * normalization_factor,
                "food": food_text
            })
    
    return ingredients

# Function to connect to a nutrition database (placeholder)
def get_macro_data(food_name):
    """
    This function would connect to a nutrition database API
    or a local database to get macro information for a food
    Returns dummy data for demonstration
    """
    # Dummy database for demonstration
    food_db = {
        "rice": {"carbs": 28, "protein": 2.7, "fat": 0.3, "sugar": 0.1, "per_100g": True},
        "chicken": {"carbs": 0, "protein": 31, "fat": 3.6, "sugar": 0, "per_100g": True},
        "apple": {"carbs": 14, "protein": 0.3, "fat": 0.2, "sugar": 10, "per_100g": True},
        "milk": {"carbs": 5, "protein": 3.4, "fat": 3.6, "sugar": 5, "per_100g": True}
    }
    
    # Basic fuzzy matching - find the closest food in our database
    for db_food in food_db:
        if db_food in food_name.lower():
            return food_db[db_food]
    
    # Return default values if food not found
    return {"carbs": 0, "protein": 0, "fat": 0, "sugar": 0, "per_100g": True}


def calculate_macros(ingredients):
    total_macros = {"carbs": 0, "protein": 0, "fat": 0, "sugar": 0}
    
    for item in ingredients:
        food_macros = get_macro_data(item["food"])
        factor = item["normalized_quantity"] / 100 if food_macros["per_100g"] else item["normalized_quantity"]
        
        total_macros["carbs"] += food_macros["carbs"] * factor
        total_macros["protein"] += food_macros["protein"] * factor
        total_macros["fat"] += food_macros["fat"] * factor
        total_macros["sugar"] += food_macros["sugar"] * factor
    
    return total_macros

# Complete analysis function
def analyze_food_diary(text):
    ingredients = extract_food_info(text)
    macros = calculate_macros(ingredients)
    
    return {
        "ingredients": ingredients,
        "macros": macros
    }

# Test with examples
test_texts = [
    "I ate 2 cups of rice and 8 oz of chicken.",
    "For breakfast I had 1/2 cup oatmeal with a banana and 1 tbsp of honey.",
    "Lunch was a turkey sandwich with 2 slices of whole wheat bread and 3 oz turkey breast."
]

for text in test_texts:
    result = analyze_food_diary(text)
    print(f"\nAnalysis for: '{text}'")
    print("Extracted ingredients:")
    for ing in result["ingredients"]:
        print(f"- {ing['quantity']} {ing['unit']} of {ing['food']} (normalized: {ing['normalized_quantity']}g)")
    print("Calculated macros:")
    for macro, value in result["macros"].items():
        print(f"- {macro}: {value:.1f}g")