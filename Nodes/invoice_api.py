from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api_routes import router as invoice_router

app = FastAPI(
    title="Invoice Extraction API",
    description="API for extracting structured data from invoice PDFs",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(invoice_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("invoice_api:app", host="0.0.0.0", port=8000, reload=True)
