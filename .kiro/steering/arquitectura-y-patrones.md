# Arquitectura y Patrones de Desarrollo

## Principios Arquitectónicos Fundamentales

### 1. Separación de Responsabilidades
El proyecto ChatGPT-API-Scanner sigue una arquitectura modular clara donde cada componente tiene responsabilidades específicas:

- **`main.py`**: Punto de entrada principal y lógica de escaneo con Selenium WebDriver
- **`manager.py`**: Gestión de datos (DatabaseManager) y cookies (CookieManager)
- **`utils.py`**: Funciones utilitarias y helpers compartidos
- **`configs.py`**: Configuraciones centralizadas del sistema

### 2. Patrón Context Manager
**OBLIGATORIO**: Todos los recursos que requieren limpieza deben implementar el patrón Context Manager:

```python
class DatabaseManager:
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        if self.con:
            self.con.close()
```

**Reglas de implementación**:
- Siempre usar `with` statements para DatabaseManager
- Implementar `__enter__` y `__exit__` en clases que manejen recursos
- Garantizar limpieza de recursos incluso en caso de excepciones

### 3. Gestión de Recursos del WebDriver
El WebDriver de Selenium debe ser gestionado cuidadosamente:

```python
def __del__(self):
    if hasattr(self, "driver") and self.driver is not None:
        self.driver.quit()
```

**Mejores prácticas**:
- Siempre verificar existencia del driver antes de cerrarlo
- Usar `driver.quit()` en lugar de `driver.close()` para limpieza completa
- Implementar timeout apropiados para operaciones web

### 4. Arquitectura de Base de Datos
El sistema utiliza SQLite con un esquema simple pero efectivo:

**Estructura requerida**:
- Tabla principal para almacenar claves API y su estado
- Tabla secundaria para URLs procesadas (evitar duplicados)
- Índices apropiados para consultas frecuentes

**Operaciones críticas**:
- `key_exists()`: Verificación de duplicados antes de inserción
- `deduplicate()`: Limpieza periódica de registros duplicados
- `all_keys()` vs `all_iq_keys()`: Diferentes vistas de los datos

## Patrones de Manejo de Errores

### 1. Rate Limiting y Reintentos
Implementar estrategias robustas para manejar límites de API:

```python
# Patrón recomendado para reintentos
import time
from functools import wraps

def retry_on_rate_limit(max_retries=3, delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except RateLimitError:
                    if attempt < max_retries - 1:
                        time.sleep(delay * (2 ** attempt))  # Exponential backoff
                    else:
                        raise
            return wrapper
    return decorator
```

### 2. Validación de Claves API
Todas las claves API deben ser validadas antes del procesamiento:

**Formatos soportados**:
- Claves legacy: `sk-...`
- Claves de proyecto nuevas: formato actualizado post-agosto 2024
- Validación de longitud y caracteres permitidos

### 3. Manejo de Excepciones de Selenium
Implementar manejo específico para errores comunes de WebDriver:

```python
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException
)

try:
    # Operación de Selenium
    pass
except TimeoutException:
    # Manejar timeout específicamente
    pass
except NoSuchElementException:
    # Elemento no encontrado
    pass
except WebDriverException as e:
    # Error general del WebDriver
    pass
```

## Estándares de Configuración

### 1. Gestión Centralizada de Configuraciones
Todas las configuraciones deben estar centralizadas en `configs.py`:

**Categorías requeridas**:
- Configuraciones de base de datos (nombre archivo, timeouts)
- Configuraciones de Selenium (timeouts, user agents, etc.)
- Configuraciones de API (endpoints, rate limits)
- Configuraciones de logging y debugging

### 2. Variables de Entorno
Para información sensible, usar variables de entorno:

```python
import os
from typing import Optional

def get_config_value(key: str, default: Optional[str] = None) -> str:
    """Obtener valor de configuración con fallback a default."""
    return os.getenv(key, default)
```

### 3. Validación de Configuraciones
Implementar validación al inicio de la aplicación:

```python
def validate_config():
    """Validar que todas las configuraciones requeridas estén presentes."""
    required_configs = ['DATABASE_PATH', 'SELENIUM_TIMEOUT']
    missing = [cfg for cfg in required_configs if not get_config_value(cfg)]
    if missing:
        raise ConfigurationError(f"Configuraciones faltantes: {missing}")
```

## Principios de Seguridad

### 1. Manejo Seguro de Cookies
Las cookies de GitHub contienen información sensible:

```python
class CookieManager:
    def save(self):
        # Encriptar cookies antes de guardar
        # Usar permisos restrictivos en archivos
        pass
    
    def load(self):
        # Validar integridad de cookies
        # Manejar cookies expiradas graciosamente
        pass
```

### 2. Sanitización de Datos
Todos los datos de entrada deben ser sanitizados:

- URLs de GitHub: validar formato y dominio
- Claves API: validar formato antes de almacenar
- Datos de base de datos: usar prepared statements

### 3. Logging Seguro
Nunca registrar información sensible en logs:

```python
import logging

# CORRECTO
logger.info(f"Procesando repositorio: {repo_name}")

# INCORRECTO - No hacer esto
logger.info(f"Clave API encontrada: {api_key}")  # ¡NUNCA!
```

## Estándares de Performance

### 1. Optimización de Base de Datos
- Usar transacciones para operaciones batch
- Implementar índices apropiados
- Realizar VACUUM periódico en SQLite

### 2. Optimización de Selenium
- Reutilizar instancias de WebDriver cuando sea posible
- Usar waits explícitos en lugar de sleeps
- Implementar pool de drivers para paralelización

### 3. Gestión de Memoria
- Limpiar objetos grandes después de uso
- Monitorear uso de memoria en scans largos
- Implementar garbage collection manual si es necesario

## Patrones de Testing

### 1. Testing de Componentes de Base de Datos
```python
import tempfile
import unittest

class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.db_manager = DatabaseManager(self.temp_db.name)
    
    def tearDown(self):
        os.unlink(self.temp_db.name)
```

### 2. Mocking de Selenium
Usar mocks para testing sin navegador real:

```python
from unittest.mock import Mock, patch

@patch('selenium.webdriver.Chrome')
def test_scanner_functionality(mock_driver):
    mock_driver.return_value = Mock()
    # Test logic here
```

### 3. Testing de Integración
Crear tests que validen la integración entre componentes:

- DatabaseManager + CookieManager
- Scanner + DatabaseManager
- Validación end-to-end con datos de prueba

Estos patrones y principios deben ser seguidos consistentemente en todo el desarrollo del proyecto para mantener la calidad, seguridad y mantenibilidad del código.