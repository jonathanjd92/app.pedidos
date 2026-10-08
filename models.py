from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Mesa(Base):
    __tablename__ = "mesas"

    id = Column(Integer, primary_key=True, index=True)
    numero_mesa = Column(String(10), unique=True, nullable=False)
    estado = Column(String(20), default="disponible")


class Categoria(Base):
    __tablename__ = "categorias"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(50), nullable=False)
    descripcion = Column(String(255))
    productos = relationship("Producto", back_populates="categoria")


class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    precio = Column(Float, nullable=False)
    disponible = Column(Boolean, default=True)
    imagen_url = Column(String(255), nullable=True)
    categoria_id = Column(Integer, ForeignKey("categorias.id"))
    stock = Column(Integer, default=0)

    #  ESTA LÍNEA ES LA QUE FALTABA:
    categoria = relationship("Categoria", back_populates="productos")  # <-- Agregar esta columna

class Pedido(Base):
    __tablename__ = "pedidos"

    id = Column(Integer, primary_key=True, index=True)
    mesa_id = Column(Integer, ForeignKey("mesas.id"), nullable=False)
    estado = Column(String(20), default="recibido")
    total = Column(Float, default=0.0)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    detalles = relationship("DetallePedido", back_populates="pedido")

class DetallePedido(Base):
    __tablename__ = "detalles_pedido"

    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Integer, nullable=False, default=1)
    precio_unitario = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)
    notas = Column(String(255), nullable=True)

    pedido = relationship("Pedido", back_populates="detalles")
    producto = relationship("Producto")

    # En models.py
estado = Column(String(20), default="PENDIENTE")