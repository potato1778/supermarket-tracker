"""Shopping categories and how to compare within them.

A category answers three questions:

  match / exclude       which offers belong to it (matched against the folded
                        product name, so "Kyckling" and "KYCKLING" both hit)
  allowed_base_units    which offers are allowed into the ranking at all
  canonical_unit        what the ranking is expressed in

The unit list is the important part. Laundry detergent comes as liquid
(litres), powder (kilograms) and pods (pieces). There is no honest way to rank
those together, so each category declares which unit it compares and the rest
are left out. A category that needs to cover several units should be split.

Categories ending up in base_unit "piece" cannot be compared by unit price at
all until pack size is read out of the product name ("24 rullar", "6-pack").
Those are listed separately in NEEDS_SPEC_PARSING.
"""

CATEGORIES = {
    # --- by weight: comparable as kr/kg ---
    "kyckling": {
        "labels": {"sv": "Kyckling", "en": "Chicken", "zh": "鸡肉"},
        "match": ["kyckling"],
        "exclude": ["kattmat", "hundmat", "katt", "hund"],
        "allowed_base_units": ["kilogram"],
        "canonical_unit": "kg",
    },
    "notkott": {
        "labels": {"sv": "Nötkött", "en": "Beef", "zh": "牛肉"},
        "match": ["nötkött", "nötfärs", "entrecote", "biff", "stek"],
        "exclude": ["kattmat", "hundmat"],
        "allowed_base_units": ["kilogram"],
        "canonical_unit": "kg",
    },
    "flask": {
        "labels": {"sv": "Fläsk", "en": "Pork", "zh": "猪肉"},
        "match": ["fläsk", "fläskfilé", "fläskkotlett", "bacon", "skinka"],
        "exclude": ["kattmat", "hundmat"],
        "allowed_base_units": ["kilogram"],
        "canonical_unit": "kg",
    },
    "fars": {
        "labels": {"sv": "Färs", "en": "Minced meat", "zh": "肉糜"},
        "match": ["färs", "köttfärs", "blandfärs"],
        "exclude": ["kattmat", "hundmat"],
        "allowed_base_units": ["kilogram"],
        "canonical_unit": "kg",
    },
    "fisk": {
        "labels": {"sv": "Fisk", "en": "Fish", "zh": "鱼"},
        "match": ["lax", "torsk", "fisk", "sej", "räkor", "tonfisk"],
        "exclude": ["kattmat", "hundmat", "fiskpinnar"],
        "allowed_base_units": ["kilogram"],
        "canonical_unit": "kg",
    },
    "ost": {
        "labels": {"sv": "Ost", "en": "Cheese", "zh": "奶酪"},
        "match": ["ost", "herrgård", "greve", "präst"],
        "exclude": ["kattmat", "hundmat", "ostkaka"],
        "allowed_base_units": ["kilogram"],
        "canonical_unit": "kg",
    },
    "kaffe": {
        "labels": {"sv": "Kaffe", "en": "Coffee", "zh": "咖啡"},
        "match": ["kaffe", "kaffebönor"],
        "exclude": ["kaffebryggare", "kaffemaskin"],
        "allowed_base_units": ["kilogram"],
        "canonical_unit": "kg",
    },
    "smor": {
        "labels": {"sv": "Smör & margarin", "en": "Butter", "zh": "黄油"},
        "match": ["smör", "margarin", "bregott"],
        "exclude": ["jordnötssmör"],
        "allowed_base_units": ["kilogram"],
        "canonical_unit": "kg",
    },
    "frukt_gront": {
        "labels": {"sv": "Frukt & grönt", "en": "Fruit & vegetables", "zh": "水果蔬菜"},
        "match": ["banan", "äpple", "tomat", "gurka", "paprika", "potatis", "lök", "apelsin"],
        "exclude": ["kattmat", "hundmat"],
        "allowed_base_units": ["kilogram"],
        "canonical_unit": "kg",
    },

    # --- by volume: comparable as kr/l ---
    "mjolk": {
        "labels": {"sv": "Mjölk", "en": "Milk", "zh": "牛奶"},
        "match": ["mjölk", "filmjölk", "gräddfil", "yoghurt", "fil"],
        "exclude": ["mjölkchoklad", "choklad"],
        "allowed_base_units": ["liter"],
        "canonical_unit": "l",
    },
    "gradde": {
        "labels": {"sv": "Grädde", "en": "Cream", "zh": "奶油"},
        "match": ["grädde", "vispgrädde", "matgrädde"],
        "exclude": [],
        "allowed_base_units": ["liter"],
        "canonical_unit": "l",
    },
    "olja": {
        "labels": {"sv": "Matolja", "en": "Cooking oil", "zh": "食用油"},
        "match": ["olja", "olivolja", "rapsolja"],
        "exclude": ["olivolja"],
        "allowed_base_units": ["liter"],
        "canonical_unit": "l",
    },
    "diskmedel": {
        "labels": {"sv": "Diskmedel", "en": "Dish soap", "zh": "洗洁精"},
        "match": ["diskmedel", "handdisk"],
        "exclude": ["diskmaskin"],
        "allowed_base_units": ["liter"],
        "canonical_unit": "l",
    },

    # --- liquid laundry detergent only; powder and pods are separate ---
    "tvattmedel_flytande": {
        "labels": {"sv": "Flytande tvättmedel", "en": "Liquid laundry detergent", "zh": "洗衣液"},
        "match": ["tvättmedel", "flytande tvättmedel", "kulörtvättmedel"],
        "exclude": ["pulver", "kapslar", "tabletter"],
        "allowed_base_units": ["liter"],
        "canonical_unit": "l",
    },
    "tvattmedel_pulver": {
        "labels": {"sv": "Tvättmedel pulver", "en": "Laundry powder", "zh": "洗衣粉"},
        "match": ["tvättmedel", "tvätt pulver"],
        "exclude": ["flytande", "kapslar"],
        "allowed_base_units": ["kilogram"],
        "canonical_unit": "kg",
    },
}

# Categories whose offers are priced per piece. Unit price is meaningless here
# until pack size is extracted from the product name, so they are excluded from
# rankings for now. Extracting that spec is the first real LLM task in this
# project, and it is also what Lidl needs.
NEEDS_SPEC_PARSING = {
    "agg": {
        "labels": {"sv": "Ägg", "en": "Eggs", "zh": "鸡蛋"},
        "match": ["ägg"],
        "exclude": ["äggnudlar"],
    },
    "toalettpapper": {
        "labels": {"sv": "Toalettpapper", "en": "Toilet paper", "zh": "卫生纸"},
        "match": ["toalettpapper", "hushållspapper"],
        "exclude": [],
    },
}


def get(key):
    """Look up a rankable category, or raise with a helpful message."""
    if key not in CATEGORIES:
        known = ", ".join(sorted(CATEGORIES))
        raise KeyError(f"unknown category '{key}'. Known: {known}")
    return CATEGORIES[key]


def all_keys():
    return sorted(CATEGORIES)
