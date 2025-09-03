from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Decree(BaseModel):
    title: str = Field(..., description="The title of the decree")
    content: str = Field(..., description="The content of the decree")
    source_url: str = Field(..., description="The source url of the decree")
    valid_date: Optional[datetime] = Field(..., description="The valid date of the decree")
    public_date: Optional[datetime] = Field(..., description="The public date of the decree")


class Decrees(BaseModel):
    data: list[Decree]