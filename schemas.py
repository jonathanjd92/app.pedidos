from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# --- ESQUEMAS DE PRODUCTO ---
class ProductoBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    precio: float = Field(gt=0, description="El precio debe ser mayor a 0")
    disponible: Optional[bool] = True

class ProductoCreate(ProductoBase):
    categoria_id: Optional[int] = None

class ProductoResponse(ProductoBase):
    id: int

    class Config:
        from_attributes = True


# --- ESQUEMAS DE DETALLE DE PEDIDO (Renglón) ---
class DetallePedidoCreate(BaseModel):
    producto_id: int
    cantidad: int = Field(ge=1, description="La cantidad debe ser al menos 1")
    notas: Optional[str] = None  # Ej: "Sin cebolla"

class DetallePedidoResponse(BaseModel):
    id: int
    producto_id: int
    cantidad: int
    precio_unitario: float
    subtotal: float
    notas: Optional[str] = None

    class Config:
        from_attributes = True


# --- ESQUEMAS DE PEDIDO (Cabecera) ---
class PedidoCreate(BaseModel):
    mesa_id: int
    detalles: List[DetallePedidoCreate]  # Lista de productos incluidos en el pedido

class PedidoResponse(BaseModel):
    id: int
    mesa_id: int
    estado: str
    total: float
    fecha_creacion: datetime
    detalles: List[DetallePedidoResponse] = []

    class Config:
        from_attributes = True


# --- ESQUEMAS DE CATEGORÍA ---
class CategoriaBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None

class CategoriaCreate(CategoriaBase):
    pass

class CategoriaResponse(CategoriaBase):
    id: int

    class Config:
        from_attributes = True


# --- ESQUEMAS DE MESA ---
class MesaBase(BaseModel):
    numero_mesa: str

class MesaCreate(MesaBase):
    pass

class MesaResponse(MesaBase):
    id: int
    estado: str

    class Config:
        from_attributes = True