import time
from typing import Literal, Annotated
from pydantic import BaseModel, Field, ConfigDict, model_validator
Number=Annotated[float, Field(allow_inf_nan=False)]
Id=Annotated[str,Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_.-]+$')]
class GasMetrics(BaseModel):
    model_config=ConfigDict(extra='forbid')
    CO: Number|None=None
    H2: Number|None=None
    VOC: Number|None=None
class Thermal(BaseModel):
    model_config=ConfigDict(extra='forbid')
    max_c: Number|None=None
    mean_c: Number|None=None
    hotspot: bool|None=None
    frame_width: int|None=Field(None,ge=1,le=640)
    frame_height: int|None=Field(None,ge=1,le=640)
class Telemetry(BaseModel):
    model_config=ConfigDict(extra='forbid')
    node_id: Id
    sequence_no: int=Field(ge=0,le=2**63-1)
    boot_id: Id='legacy'
    timestamp: int=Field(default_factory=lambda:int(time.time()),ge=0,le=4102444800)
    source: Literal['measured','demo','unknown']='unknown'
    gas_data: GasMetrics|None=None
    gas_unit: Literal['ppm','index','unknown']='unknown'
    raw_data: dict[str,Number]|None=None
    environment: dict[str,Number]|None=None
    thermal: Thermal|None=None
    camera_azimuth: Number|None=Field(None,ge=0,lt=360)
    latitude: Number|None=Field(None,ge=-90,le=90)
    longitude: Number|None=Field(None,ge=-180,le=180)
    rssi: Number|None=None
    snr: Number|None=None
    @model_validator(mode='after')
    def validate_packet(self):
        if (self.latitude is None)!=(self.longitude is None): raise ValueError('latitude and longitude must be supplied together')
        if not any([self.gas_data and any(v is not None for v in self.gas_data.model_dump().values()),self.raw_data,self.environment,self.thermal]): raise ValueError('No observations')
        for x in (self.raw_data,self.environment):
            if x and (len(x)>50 or any(len(k)>60 for k in x)): raise ValueError('Too many observation fields')
        return self
class WorkerPing(BaseModel):
    worker_id: Id
    model_id: str=Field(min_length=1,max_length=160)
    state: Literal['READY','STOPPED']='READY'
class Claim(BaseModel):
    worker_id: Id
    model_id: str=Field(min_length=1,max_length=160)
class Lease(BaseModel):
    claim_token: str=Field(pattern=r'^[a-f0-9]{32}$')
class Failure(Lease):
    error: str=Field(min_length=1,max_length=1000)
