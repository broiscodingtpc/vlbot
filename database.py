from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import config

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    username = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    sessions = relationship("Session", back_populates="user")

class Session(Base):
    __tablename__ = 'sessions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    token_ca = Column(String, nullable=False)
    strategy = Column(String, default="medium") # slow, medium, fast
    
    # Deposit Wallet (Generated for this session)
    deposit_wallet_address = Column(String, unique=True)
    deposit_wallet_private_key = Column(String) # Encrypted in prod, plain for MVP
    
    # State
    is_active = Column(Boolean, default=False)
    total_volume_generated = Column(Float, default=0.0)
    telegram_chat_id = Column(String)  # For restoring notifications on restart
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="sessions")
    sub_wallets = relationship("SubWallet", back_populates="session")

class SubWallet(Base):
    __tablename__ = 'sub_wallets'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('sessions.id'))
    address = Column(String)
    private_key = Column(String)
    
    session = relationship("Session", back_populates="sub_wallets")

# Setup
engine = create_engine(config.DB_PATH)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
