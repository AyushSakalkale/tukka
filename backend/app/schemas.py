from pydantic import BaseModel
from typing import List, Optional

class InfoRequest(BaseModel):
    url: str

class FormatOption(BaseModel):
    id: str
    label: str
    size: Optional[str] = "Unknown size"
    type: str  # "video" or "audio"
    ext: str

class InfoResponse(BaseModel):
    title: str
    channel: str
    duration: str
    thumbnail: Optional[str] = None
    formats: List[FormatOption]

class DownloadRequest(BaseModel):
    url: str
    format_id: str

class DownloadResponse(BaseModel):
    task_id: str
