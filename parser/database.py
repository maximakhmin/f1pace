from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, text
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()

class Tracks(Base):
    __tablename__ = 'tracks'
    id = Column(Integer, primary_key=True)
    circuit_id = Column(String)
    country = Column(String)
    location = Column(String)
    circuit_name = Column(String)
    lat = Column(Float)
    long = Column(Float)

class Events(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True)
    circuit_id = Column(Integer, ForeignKey('tracks.id'))
    year = Column(Integer)
    round = Column(Integer)
    is_sprint = Column(Boolean)

class SessionTypes(Base):
    __tablename__ = 'session_types'
    id = Column(Integer, primary_key=True) 
    name = Column(String)

class Session(Base):
    __tablename__ = 'sessions'
    id = Column(Integer, primary_key=True) 
    event_id = Column(Integer, ForeignKey('events.id'))
    session_type = Column(Integer, ForeignKey('session_types.id'))
    datetime_start_utc = Column(DateTime)


engine = create_engine(f'postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:5432/f1pace')
Base.metadata.create_all(engine)