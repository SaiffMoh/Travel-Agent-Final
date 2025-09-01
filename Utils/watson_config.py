# Importing the IBM Watsonx AI client and model inference classes
from ibm_watsonx_ai import APIClient
from ibm_watsonx_ai.foundation_models import ModelInference
from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams
from ibm_watsonx_ai.foundation_models.utils.enums import DecodingMethods
from dotenv import load_dotenv
import os
load_dotenv()

def get_llm():
    MY_CRED = { "url": "https://eu-de.ml.cloud.ibm.com",
                "apikey": f"{os.getenv('WATSON_APIKEY')}"
              }
    GEN_PARAMS = {
                GenParams.DECODING_METHOD: DecodingMethods.SAMPLE,
                GenParams.MAX_NEW_TOKENS: 8192,
                GenParams.TEMPERATURE: 0
                 }
    PROJECT_ID = os.getenv("PROJECT_ID")
    client = APIClient(MY_CRED)
    print("IAM token fetched successfully!")
    llm = ModelInference(
                        model_id =  client.foundation_models.TextModels.LLAMA_3_3_70B_INSTRUCT,
                        credentials = MY_CRED,
                        params = GEN_PARAMS,
                        project_id = PROJECT_ID
                        )
    return llm

llm = get_llm()