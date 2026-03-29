from pydantic import BaseModel


class VoiceRead(BaseModel):
    id: int
    name: str
    display_name: str
    backend: str
    model_name: str
    description: str | None
    is_enabled: bool
    kind: str

    model_config = {'from_attributes': True}
