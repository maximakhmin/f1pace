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

class Tyres(Base):
    __tablename__ = 'tyres'
    id = Column(Integer, primary_key=True) 
    name = Column(String)

class TrackStatuses(Base):
    __tablename__ = 'track_statuses'
    id = Column(Integer, primary_key=True) 
    name = Column(String)
 

class Laps(Base):
    __tablename__ = 'laps'
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey('sessions.id'))

    driver_abbr = Column(String)
    driver_num = Column(Integer)

    position = Column(Integer)

    lap_time = Column(Float)
    lap_s1_time = Column(Float)
    lap_s2_time = Column(Float)
    lap_s3_time = Column(Float)
    lap_number = Column(Integer)
    stint_number = Column(Integer)
    tyre_age = Column(Integer)
    tyre_type = Column(Integer, ForeignKey('tyres.id'))
    is_deleted = Column(Boolean)

    air_temp = Column(Float)
    track_temp = Column(Float)
    humidity = Column(Float)
    is_rain = Column(Boolean)
    wind_direction = Column(Integer)
    wind_speed = Column(Float)

    track_status = Column(Integer, ForeignKey('track_statuses.id'))


engine = create_engine(f'postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:5432/f1pace')
Base.metadata.create_all(engine)