import sqlite3
import os

databases = ['db.sqlite3', 'db_nueva.sqlite3', 'db.sqlite3.broken', 'db_verify.sqlite3', 'tmp_restore.sqlite3']

for db in databases:
    if not os.path.exists(db):
        print(f"{db}: doesn't exist")
        continue
    try:
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tienda_pelicula';")
        if cursor.fetchone():
            count_movies = cursor.execute("SELECT COUNT(*) FROM tienda_pelicula").fetchone()[0]
            count_clients = cursor.execute("SELECT COUNT(*) FROM tienda_cliente").fetchone()[0]
            count_users = cursor.execute("SELECT COUNT(*) FROM auth_user").fetchone()[0]
            print(f"--- {db} ---")
            print(f"Peliculas: {count_movies}")
            print(f"Clientes:  {count_clients}")
            print(f"Usuarios:  {count_users}")
        else:
            print(f"{db}: tables not initialized yet.")
    except Exception as e:
        print(f"{db}: Error reading ({e})")
