# Diabot, made by Owen Tucker

Install requirements by running: pip install -r requirements.txt

--------------------------------------------------------

To run the Python code, you can use the following command-line arguments:

--bg: your current blood glucose level
--target: your target blood glucose level
--icr: your insulin-to-carb ratio
--cf: your correction factor
--iob: the amount of insulin on board
--cgm-data: path to a file with continuous glucose monitor (CGM) data

-----------------------------------------------------------

As well as numeric values, diabot accepts the following as measurement units: "one", "gram", 
"grams", "g", "ounce", "ounces", "oz", "pound", "pounds", "lb", "lbs", "cup", "cups", "tbsp", 
"tablespoon", "tablespoons", "tsp", "teaspoon", "teaspoons"

cgm data is cgm_data.csv 

running the code would look like this: 

python diabot.py "I ate three tablespoons of peanut butter" --bg 170 --target 100 --cgm-data cgm_data.csv