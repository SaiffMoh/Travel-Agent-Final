from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import auth, users, chat, invoices, passports, visas

app = FastAPI(
    title="Travel Agent Backend API",
    description="FastAPI backend for ask_travel authentication and chat",
    version="1.0.0"
)

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(chat.router)
app.include_router(invoices.router)
app.include_router(passports.router)
app.include_router(visas.router)

@app.get("/")
async def root():
    return {"message": "Travel Agent Backend API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
