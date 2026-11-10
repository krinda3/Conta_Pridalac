"""Servicios: operaciones que cambian la base de datos respetando las reglas contables.

Cada función recibe la sesión y **no hace commit**: quien la llama decide la transacción (una pantalla = una transacción).
"""
