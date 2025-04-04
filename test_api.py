import requests

# Replace this with your actual API key and endpoint for Gemini
API_KEY = 'AIzaSyBSMKQm6nS0iE0R9Ufreft2pbXwtd23xbg'  # Your Gemini API Key
API_URL = 'https://api.gemini.com/v1'  # Adjust to the actual endpoint you're using

def get_gemini_model():
    """Function to list available models and check if `gpt-3` or equivalent is available"""
    try:
        response = requests.get(f"{API_URL}/models", headers={"Authorization": f"Bearer {API_KEY}"})
        response.raise_for_status()  # Will raise an error if the request failed
        models = response.json()  # Assuming the response is a JSON with a list of models
        print("Available models:", models)
        return models
    except requests.exceptions.RequestException as e:
        print(f"Error fetching models: {e}")
        return None

# Fetch and print available models from Gemini
if __name__ == "__main__":
    models = get_gemini_model()
    if models:
        print("Models fetched successfully")
    else:
        print("Failed to fetch models")