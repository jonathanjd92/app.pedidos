from datetime import datetime, date
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db, engine, Base
import models
import schemas
from ws_manager import manager
from pydantic import BaseModel
from fastapi import HTTPException, status




# Crear tablas en MySQL si no existen
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Restaurante API - Sistema de Pedidos")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ENDPOINTS DE PRODUCTOS ---
@app.get("/productos", response_model=List[schemas.ProductoResponse])
def listar_productos(db: Session = Depends(get_db)):
    return db.query(models.Producto).all()

@app.post("/productos", response_model=schemas.ProductoResponse, status_code=status.HTTP_201_CREATED)
def crear_producto(producto: schemas.ProductoCreate, db: Session = Depends(get_db)):
    nuevo_producto = models.Producto(**producto.model_dump())
    db.add(nuevo_producto)
    db.commit()
    db.refresh(nuevo_producto)
    return nuevo_producto


# --- ENDPOINTS DE PEDIDOS ---
@app.post("/pedidos", response_model=schemas.PedidoResponse, status_code=status.HTTP_201_CREATED)
async def crear_pedido(pedido_in: schemas.PedidoCreate, db: Session = Depends(get_db)):
    # 1. Verificar mesa
    mesa = db.query(models.Mesa).filter(models.Mesa.id == pedido_in.mesa_id).first()
    if not mesa:
        raise HTTPException(status_code=404, detail="La mesa especificada no existe")

    # 2. Crear cabecera del pedido
    nuevo_pedido = models.Pedido(mesa_id=pedido_in.mesa_id, total=0.0, estado="PENDIENTE")
    db.add(nuevo_pedido)
    db.commit()
    db.refresh(nuevo_pedido)

    total_acumulado = 0.0
    detalles_notificacion = []

    # 3. Procesar items
    for item in pedido_in.detalles:
        prod = db.query(models.Producto).filter(models.Producto.id == item.producto_id).first()
        if not prod:
            raise HTTPException(status_code=404, detail=f"Producto ID {item.producto_id} no encontrado")

        subtotal_item = prod.precio * item.cantidad
        total_acumulado += subtotal_item

        detalle = models.DetallePedido(
            pedido_id=nuevo_pedido.id,
            producto_id=prod.id,
            cantidad=item.cantidad,
            precio_unitario=prod.precio,
            subtotal=subtotal_item,
            notas=item.notas
        )
        db.add(detalle)
        
        # Estructura simplificada para enviar a la cocina
        detalles_notificacion.append({
            "producto": prod.nombre,
            "cantidad": item.cantidad,
            "notas": item.notas
        })

    # 4. Actualizar pedido y estado de mesa
    nuevo_pedido.total = total_acumulado
    mesa.estado = "ocupada"
    db.commit()
    db.refresh(nuevo_pedido)

    # 5. NOTIFICAR A LA COCINA EN TIEMPO REAL 🚀
    await manager.broadcast({
        "evento": "NUEVO_PEDIDO",
        "pedido_id": nuevo_pedido.id,
        "mesa_id": nuevo_pedido.mesa_id,
        "fecha_creacion": datetime.now().isoformat(),
        "detalles": detalles_notificacion
    })

    return nuevo_pedido

@app.get("/cocina/pedidos-pendientes")
def obtener_pedidos_pendientes(db: Session = Depends(get_db)):
    # 1. Consultar todos los pedidos que NO estén entregados ni pagados
    pedidos = db.query(models.Pedido).filter(
        models.Pedido.estado.in_(["PENDIENTE", "pendiente"])
    ).all()
    
    resultado = []
    for p in pedidos:
        # 2. Consultar directamente los detalles de este pedido
        detalles_db = db.query(models.DetallePedido).filter(
            models.DetallePedido.pedido_id == p.id
        ).all()
        
        detalles_lista = []
        for d in detalles_db:
            prod = db.query(models.Producto).filter(models.Producto.id == d.producto_id).first()
            detalles_lista.append({
                "producto": prod.nombre if prod else f"Producto #{d.producto_id}",
                "cantidad": d.cantidad,
                "notas": d.notas
            })
            
        resultado.append({
            "pedido_id": p.id,
            "mesa_id": p.mesa_id,
            "fecha_creacion": p.fecha_creacion.isoformat() if hasattr(p, 'fecha_creacion') and p.fecha_creacion else None,
            "detalles": detalles_lista
        })
        
    return resultado

@app.get("/pedidos", response_model=List[schemas.PedidoResponse])
def listar_pedidos(db: Session = Depends(get_db)):
    return db.query(models.Pedido).all()


@app.patch("/pedidos/{pedido_id}/estado")
def cambiar_estado_pedido(pedido_id: int, nuevo_estado: str = "ENTREGADO", db: Session = Depends(get_db)):
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    pedido.estado = nuevo_estado
    db.commit()
    return {"mensaje": f"Pedido {pedido_id} actualizado a {nuevo_estado}"}

# --- ENDPOINTS DE CATEGORÍAS ---
@app.get("/categorias", response_model=List[schemas.CategoriaResponse])
def listar_categorias(db: Session = Depends(get_db)):
    return db.query(models.Categoria).all()

@app.post("/categorias", response_model=schemas.CategoriaResponse, status_code=status.HTTP_201_CREATED)
def crear_categoria(categoria: schemas.CategoriaCreate, db: Session = Depends(get_db)):
    nueva_categoria = models.Categoria(**categoria.model_dump())
    db.add(nueva_categoria)
    db.commit()
    db.refresh(nueva_categoria)
    return nueva_categoria


# --- ENDPOINTS DE MESAS ---
@app.get("/mesas", response_model=List[schemas.MesaResponse])
def listar_mesas(db: Session = Depends(get_db)):
    return db.query(models.Mesa).all()

@app.post("/mesas", response_model=schemas.MesaResponse, status_code=status.HTTP_201_CREATED)
def crear_mesa(mesa: schemas.MesaCreate, db: Session = Depends(get_db)):
    nueva_mesa = models.Mesa(**mesa.model_dump())
    db.add(nueva_mesa)
    db.commit()
    db.refresh(nueva_mesa)
    return nueva_mesa

# 1. Obtener pedidos pendientes para el panel de cocina
@app.get("/cocina/pedidos", response_model=List[schemas.PedidoResponse])
def listar_pedidos_cocina(db: Session = Depends(get_db)):
    return db.query(models.Pedido).filter(
        models.Pedido.estado.in_(["PENDIENTE", "EN_PREPARACION"])
    ).all()

# 2. Cambiar estado del pedido (ej. de PENDIENTE a EN_PREPARACION o LISTO)
@app.patch("/pedidos/{pedido_id}/estado", response_model=schemas.PedidoResponse)
def cambiar_estado_pedido(
    pedido_id: int, 
    nuevo_estado: str, # "EN_PREPARACION", "LISTO", "ENTREGADO"
    db: Session = Depends(get_db)
):
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    pedido.estado = nuevo_estado
    db.commit()
    db.refresh(pedido)
    return pedido

# 1. Obtener los pedidos pendientes de una mesa específica
# 1. Obtener la cuenta de la mesa (incluyendo pedidos PENDIENTES, LISTOS o ENTREGADOS)
@app.get("/caja/mesa/{mesa_id}")
def obtener_cuenta_mesa(mesa_id: int, db: Session = Depends(get_db)):
    # Se consulta cualquier pedido activo que NO esté marcado como PAGADO o CANCELADO
    pedidos = db.query(models.Pedido).filter(
        models.Pedido.mesa_id == mesa_id,
        models.Pedido.estado.in_(["PENDIENTE", "pendiente", "LISTO", "listo", "ENTREGADO", "entregado"])
    ).all()
    
    resultado = []
    for p in pedidos:
        detalles_db = db.query(models.DetallePedido).filter(
            models.DetallePedido.pedido_id == p.id
        ).all()
        
        detalles_lista = []
        subtotal_pedido = 0.0
        for d in detalles_db:
            prod = db.query(models.Producto).filter(models.Producto.id == d.producto_id).first()
            precio_unitario = prod.precio if prod else 0.0
            sub = precio_unitario * d.cantidad
            subtotal_pedido += sub
            
            detalles_lista.append({
                "producto_nombre": prod.nombre if prod else f"Producto #{d.producto_id}",
                "cantidad": d.cantidad,
                "precio_unitario": precio_unitario,
                "subtotal": sub
            })
            
        resultado.append({
            "pedido_id": p.id,
            "total": subtotal_pedido,
            "detalles": detalles_lista
        })
        
    return resultado

# 2. Registrar el pago y LIBERAR la mesa
@app.post("/caja/mesa/{mesa_id}/pagar")
def pagar_y_liberar_mesa(mesa_id: int, db: Session = Depends(get_db)):
    # Cambiar el estado de todos los pedidos activos de la mesa a PAGADO
    pedidos = db.query(models.Pedido).filter(
        models.Pedido.mesa_id == mesa_id,
        models.Pedido.estado.in_(["PENDIENTE", "pendiente", "LISTO", "listo", "ENTREGADO", "entregado"])
    ).all()
    
    for p in pedidos:
        p.estado = "PAGADO"
        
    # Cambiar el estado de la mesa a LIBRE
    mesa = db.query(models.Mesa).filter(models.Mesa.id == mesa_id).first()
    if mesa:
        mesa.estado = "LIBRE"  # Cambia a "DISPONIBLE" si en tu base de datos usas esa palabra
        
    db.commit()
    return {"mensaje": f"Mesa #{mesa_id} pagada y liberada con éxito"}

@app.websocket("/ws/cocina")
async def websocket_cocina(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Mantiene viva la conexión
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

from datetime import date
from sqlalchemy import func

# 1. Dashboard: Métricas principales (Total acumulado hoy, ventas, ocupación)
@app.get("/admin/metrics")
def obtener_metricas_admin(db: Session = Depends(get_db)):
    # Total recaudado de pedidos PAGADOS
    pedidos_pagados = db.query(models.Pedido).filter(
        models.Pedido.estado == "PAGADO"
    ).all()
    
    total_dinero = 0.0
    for p in pedidos_pagados:
        detalles = db.query(models.DetallePedido).filter(models.DetallePedido.pedido_id == p.id).all()
        for d in detalles:
            prod = db.query(models.Producto).filter(models.Producto.id == d.producto_id).first()
            if prod:
                total_dinero += prod.precio * d.cantidad

    # Ocupación de Mesas
    total_mesas = db.query(models.Mesa).count()
    mesas_ocupadas = db.query(models.Mesa).filter(
        models.Mesa.estado.in_(["OCUPADA", "ocupada"])
    ).count()
    
    porcentaje_ocupacion = round((mesas_ocupadas / total_mesas * 100), 1) if total_mesas > 0 else 0

    return {
        "dinero_recaudado": total_dinero,
        "ventas_totales": len(pedidos_pagados),
        "total_mesas": total_mesas,
        "mesas_ocupadas": mesas_ocupadas,
        "porcentaje_ocupacion": porcentaje_ocupacion
    }

# 2. Inventario: Crear o actualizar stock de producto
@app.put("/admin/producto/{producto_id}/stock")
def actualizar_stock_producto(producto_id: int, nuevo_stock: int, db: Session = Depends(get_db)):
    prod = db.query(models.Producto).filter(models.Producto.id == producto_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    prod.stock = nuevo_stock
    db.commit()
    return {"mensaje": "Stock actualizado"}

# 3. Reporte de Historial de Pedidos Pagados
@app.get("/admin/ventas")
def historial_ventas(db: Session = Depends(get_db)):
    pedidos = db.query(models.Pedido).filter(models.Pedido.estado == "PAGADO").all()
    historial = []
    for p in pedidos:
        detalles = db.query(models.DetallePedido).filter(models.DetallePedido.pedido_id == p.id).all()
        total_pedido = sum([(db.query(models.Producto).get(d.producto_id).precio if db.query(models.Producto).get(d.producto_id) else 0) * d.cantidad for d in detalles])
        historial.append({
            "pedido_id": p.id,
            "mesa_id": p.mesa_id,
            "total": total_pedido,
            "estado": p.estado
        })
    return historial

# Schema para Login
class LoginData(BaseModel):
    usuario: str
    password: str

# 1. Endpoint de Autenticación
@app.post("/login")
def login(datos: LoginData):
    # Usuarios configurados (Puedes moverlos a la base de datos si lo prefieres)
    if datos.usuario == "admin" and datos.password == "admin123":
        return {"rol": "ADMIN", "nombre": "Administrador General"}
    elif datos.usuario == "inventario" and datos.password == "inv123":
        return {"rol": "ENCARGADO", "nombre": "Encargado de Inventario"}
    else:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

# 2. Filtrado de Ventas y Métricas por Fecha
from datetime import datetime

@app.get("/admin/ventas/filtrar")
def filtrar_ventas(fecha_inicio: str = None, fecha_fin: str = None, db: Session = Depends(get_db)):
    query = db.query(models.Pedido).filter(
        models.Pedido.estado.in_(["PAGADO", "pagado"])
    )
    
    if fecha_inicio and fecha_inicio.strip():
        inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d")
        query = query.filter(models.Pedido.fecha_creacion >= inicio_dt)
        
    if fecha_fin and fecha_fin.strip():
        fin_dt = datetime.strptime(f"{fecha_fin} 23:59:59", "%Y-%m-%d %H:%M:%S")
        query = query.filter(models.Pedido.fecha_creacion <= fin_dt)
        
    pedidos = query.all()
    
    resultado = []
    total_recaudado = 0.0
    
    for p in pedidos:
        monto_pedido = p.total if p.total is not None else 0.0
        total_recaudado += monto_pedido
        
        fecha_str = "N/A"
        if hasattr(p, "fecha_creacion") and p.fecha_creacion:
            if isinstance(p.fecha_creacion, datetime):
                fecha_str = p.fecha_creacion.strftime("%Y-%m-%d %H:%M:%S")
            else:
                fecha_str = str(p.fecha_creacion)
                
        resultado.append({
            "pedido_id": p.id,
            "mesa_id": p.mesa_id,
            "fecha": fecha_str,
            "total": monto_pedido
        })
        
    return {
        "ventas": resultado,
        "total_recaudado": total_recaudado,
        "cantidad_ventas": len(resultado)
    }
# 3. Crear Categoría
@app.post("/admin/categoria")
def crear_categoria(nombre: str, db: Session = Depends(get_db)):
    nueva = models.Categoria(nombre=nombre)
    db.add(nueva)
    db.commit()
    return {"mensaje": "Categoría creada con éxito"}

# 4. Crear Producto / Referencias de Bebidas
class ProductoCreate(BaseModel):
    nombre: str
    precio: float
    stock: int
    categoria_id: int

@app.post("/admin/producto")
def crear_producto(prod: ProductoCreate, db: Session = Depends(get_db)):
    nuevo_prod = models.Producto(
        nombre=prod.nombre,
        precio=prod.precio,
        stock=prod.stock,
        categoria_id=prod.categoria_id
    )
    db.add(nuevo_prod)
    db.commit()
    return {"mensaje": "Producto guardado con éxito"}

# Esquemas de entrada (Pydantic)
class ProductoCreate(BaseModel):
    nombre: str
    precio: float
    categoria: Optional[str] = "General"
    imagen_url: Optional[str] = None
    disponible: Optional[bool] = True

class ProductoUpdate(BaseModel):
    nombre: Optional[str] = None
    precio: Optional[float] = None
    categoria: Optional[str] = None
    imagen_url: Optional[str] = None
    disponible: Optional[bool] = None

# 1. OBTENER TODOS LOS PRODUCTOS
@app.get("/productos")
def listar_productos(db: Session = Depends(get_db)):
    return db.query(models.Producto).all()

# 3. ACTUALIZAR UN PRODUCTO
@app.put("/admin/productos/{producto_id}")
def actualizar_producto(producto_id: int, prod: ProductoUpdate, db: Session = Depends(get_db)):
    producto = db.query(models.Producto).filter(models.Producto.id == producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    if prod.nombre is not None:
        producto.nombre = prod.nombre
    if prod.precio is not None:
        producto.precio = prod.precio
    if prod.categoria is not None:
        producto.categoria = prod.categoria
    if prod.imagen_url is not None:
        producto.imagen_url = prod.imagen_url
    if prod.disponible is not None:
        producto.disponible = prod.disponible

    db.commit()
    db.refresh(producto)
    return producto

# 4. ELIMINAR UN PRODUCTO
@app.delete("/admin/productos/{producto_id}")
def eliminar_producto(producto_id: int, db: Session = Depends(get_db)):
    producto = db.query(models.Producto).filter(models.Producto.id == producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    db.delete(producto)
    db.commit()
    return {"mensaje": f"Producto con ID {producto_id} eliminado correctamente"}

# 5. Crear Mesas
@app.post("/admin/mesa")
def crear_mesa(numero: int, db: Session = Depends(get_db)):
    nueva_mesa = models.Mesa(numero=numero, estado="LIBRE")
    db.add(nueva_mesa)
    db.commit()
    return {"mensaje": "Mesa agregada con éxito"}

from datetime import datetime

@app.get("/admin/ventas/filtrar")
def filtrar_ventas(fecha_inicio: str = None, fecha_fin: str = None, db: Session = Depends(get_db)):
    query = db.query(models.Pedido).filter(
        models.Pedido.estado.in_(["PAGADO", "pagado"])
    )
    
    # Filtrar por fecha_creacion
    if fecha_inicio and fecha_inicio.strip():
        inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d")
        query = query.filter(models.Pedido.fecha_creacion >= inicio_dt)
        
    if fecha_fin and fecha_fin.strip():
        fin_dt = datetime.strptime(f"{fecha_fin} 23:59:59", "%Y-%m-%d %H:%M:%S")
        query = query.filter(models.Pedido.fecha_creacion <= fin_dt)
        
    pedidos = query.all()
    
    resultado = []
    total_recaudado = 0.0
    
    for p in pedidos:
        # Usa el campo total del pedido directamente, o 0.0 si está vacío
        monto_pedido = p.total if p.total is not None else 0.0
        total_recaudado += monto_pedido
        
        # Formatear la fecha usando fecha_creacion
        fecha_str = "N/A"
        if hasattr(p, "fecha_creacion") and p.fecha_creacion:
            if isinstance(p.fecha_creacion, datetime):
                fecha_str = p.fecha_creacion.strftime("%Y-%m-%d %H:%M:%S")
            else:
                fecha_str = str(p.fecha_creacion)
                
        resultado.append({
            "pedido_id": p.id,
            "mesa_id": p.mesa_id,
            "fecha_creacion": fecha_str,
            "total": monto_pedido
        })
        
    return {
        "ventas": resultado,
        "total_recaudado": total_recaudado,
        "cantidad_ventas": len(resultado)
    }