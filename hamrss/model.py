from pydantic import BaseModel


class Product(BaseModel):
    url: str
    title: str
    description: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    product_id: str | None = None
    location: str | None = None
    date_added: str | None = None
    price: str | None = None
    image_url: str | None = None
    author: str | None = None
