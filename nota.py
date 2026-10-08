 async function guardarProducto() {
            const prod = {
                nombre: document.getElementById("pNombre").value,
                precio: parseFloat(document.getElementById("pPrecio").value),
                stock: parseInt(document.getElementById("pStock").value),
                categoria_id: parseInt(document.getElementById("pCategoria").value)
            };

            const res = await fetch(`${API_URL}/admin/producto`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(prod)
            });

            if (res.ok) {
                alert("Producto registrado con éxito");
                cargarTablaProductos();
            }
        }