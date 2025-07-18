# Estándares de Código y Mejores Prácticas

## Configuración de Herramientas de Calidad

El proyecto utiliza múltiples herramientas de linting y formateo que deben ser respetadas:

### 1. Flake8 (`.flake8`)
Configuración para verificación de estilo PEP8:
- Longitud máxima de línea: seguir configuración existente
- Ignorar errores específicos según configuración del proyecto
- Ejecutar antes de cada commit

### 2. Pylint (`.pylintrc`)
Análisis estático avanzado:
- Seguir todas las reglas configuradas en `.pylintrc`
- Mantener score mínimo de calidad
- Documentar excepciones cuando sea necesario

### 3. Ruff (`.ruff.toml`)
Linter moderno y rápido:
- Configuración más estricta que Flake8
- Corrección automática cuando sea posible
- Integrar en workflow de desarrollo

### 4. Pre-commit Hooks (`.pre-commit-config.yaml`)
**OBLIGATORIO**: Todos los commits deben pasar los hooks configurados:

```bash
# Instalar pre-commit hooks
pre-commit install

# Ejecutar manualmente
pre-commit run --all-files
```

## Estándares de Nomenclatura

### 1. Convenciones de Nombres

**Clases**: PascalCase
```python
class DatabaseManager:
class CookieManager:
class APIKeyValidator:
```

**Funciones y métodos**: snake_case
```python
def verify_user_login():
def all_iq_keys():
def key_exists():
```

**Variables**: snake_case
```python
api_key = "sk-..."
db_filename = "github.db"
max_retries = 3
```

**Constantes**: UPPER_SNAKE_CASE
```python
DEFAULT_TIMEOUT = 30
MAX_RETRY_ATTEMPTS = 5
DATABASE_NAME = "github.db"
```

### 2. Nombres Descriptivos y Específicos

**CORRECTO**:
```python
def validate_openai_api_key(api_key: str) -> bool:
def get_github_repositories_from_search(query: str) -> list:
def store_api_key_with_status(api_key: str, status: str) -> None:
```

**INCORRECTO**:
```python
def validate(key):  # Muy genérico
def get_repos(q):   # Abreviaciones no claras
def store(k, s):    # Nombres de parámetros no descriptivos
```

### 3. Prefijos y Sufijos Consistentes

**Para métodos booleanos**: usar `is_`, `has_`, `can_`, `should_`
```python
def is_valid_api_key(key: str) -> bool:
def has_github_access() -> bool:
def can_access_repository(repo_url: str) -> bool:
```

**Para métodos de obtención**: usar `get_`, `fetch_`, `retrieve_`
```python
def get_api_key_status(key: str) -> str:
def fetch_repository_data(repo_url: str) -> dict:
def retrieve_stored_cookies() -> dict:
```

## Documentación de Código

### 1. Docstrings Obligatorios

**Para todas las clases**:
```python
class DatabaseManager:
    """
    Gestor de base de datos para almacenar y recuperar claves API de OpenAI.
    
    Esta clase maneja todas las operaciones de base de datos incluyendo:
    - Almacenamiento de claves API con su estado de validación
    - Deduplicación de registros
    - Gestión de URLs procesadas
    
    Attributes:
        db_filename (str): Ruta al archivo de base de datos SQLite
        con: Conexión activa a la base de datos
    
    Example:
        with DatabaseManager("github.db") as db:
            db.insert("sk-example", "valid")
            keys = db.all_keys()
    """
```

**Para métodos públicos**:
```python
def insert(self, api_key: str, status: str) -> None:
    """
    Inserta una nueva clave API con su estado en la base de datos.
    
    Args:
        api_key (str): La clave API de OpenAI a almacenar
        status (str): Estado de la clave ('valid', 'invalid', 'expired', etc.)
    
    Raises:
        DatabaseError: Si ocurre un error durante la inserción
        ValueError: Si la clave API tiene formato inválido
    
    Note:
        Este método no verifica duplicados. Usar key_exists() antes de insertar.
    """
```

### 2. Comentarios Inline

**Para lógica compleja**:
```python
def scan_github_repository(self, repo_url: str):
    # Configurar timeouts específicos para repositorios grandes
    self.driver.set_page_load_timeout(60)
    
    # GitHub implementó protección push en agosto 2024
    # Necesitamos buscar en commits anteriores a esa fecha
    cutoff_date = datetime(2024, 8, 1)
    
    # Usar XPath específico para evitar elementos dinámicos
    api_key_pattern = r'sk-[A-Za-z0-9]{48}'
```

### 3. Documentación de Configuraciones

**En `configs.py`**:
```python
# Configuraciones de Selenium WebDriver
SELENIUM_TIMEOUT = 30  # Timeout en segundos para operaciones web
SELENIUM_IMPLICIT_WAIT = 10  # Espera implícita para elementos
SELENIUM_PAGE_LOAD_TIMEOUT = 60  # Timeout para carga de páginas

# Configuraciones de Base de Datos
DATABASE_NAME = "github.db"  # Nombre del archivo SQLite
DATABASE_TIMEOUT = 30  # Timeout para operaciones de DB en segundos
MAX_CONNECTIONS = 1  # SQLite no soporta múltiples escritores

# Configuraciones de Rate Limiting
GITHUB_REQUEST_DELAY = 1  # Delay entre requests a GitHub (segundos)
OPENAI_API_RATE_LIMIT = 60  # Requests por minuto a OpenAI API
MAX_RETRY_ATTEMPTS = 3  # Intentos máximos para requests fallidos
```

## Type Hints Obligatorios

### 1. Todas las funciones deben tener type hints

```python
from typing import List, Dict, Optional, Union, Tuple

def process_api_keys(keys: List[str]) -> Dict[str, str]:
    """Procesa lista de claves y retorna diccionario con estados."""
    pass

def get_repository_info(url: str) -> Optional[Dict[str, Union[str, int]]]:
    """Obtiene información del repositorio, None si no existe."""
    pass

def validate_and_store(api_key: str, force: bool = False) -> Tuple[bool, str]:
    """Valida clave y la almacena. Retorna (éxito, mensaje)."""
    pass
```

### 2. Type hints para atributos de clase

```python
from typing import Optional
import sqlite3

class DatabaseManager:
    def __init__(self, db_filename: str) -> None:
        self.db_filename: str = db_filename
        self.con: Optional[sqlite3.Connection] = None
        self._is_connected: bool = False
```

### 3. Usar Union y Optional apropiadamente

```python
from typing import Union, Optional

# Para valores que pueden ser None
def get_api_key_status(key: str) -> Optional[str]:
    pass

# Para múltiples tipos posibles
def process_response(response: Union[dict, list, str]) -> bool:
    pass
```

## Manejo de Excepciones

### 1. Excepciones Específicas

**Crear excepciones personalizadas**:
```python
class APIKeyError(Exception):
    """Excepción base para errores relacionados con claves API."""
    pass

class InvalidAPIKeyFormat(APIKeyError):
    """Excepción para claves API con formato inválido."""
    pass

class APIKeyExpired(APIKeyError):
    """Excepción para claves API expiradas."""
    pass

class DatabaseConnectionError(Exception):
    """Excepción para errores de conexión a base de datos."""
    pass
```

### 2. Manejo Granular de Excepciones

```python
def validate_api_key(api_key: str) -> str:
    """
    Valida una clave API de OpenAI.
    
    Returns:
        str: Estado de la clave ('valid', 'invalid', 'expired')
    
    Raises:
        InvalidAPIKeyFormat: Si el formato de la clave es inválido
        APIConnectionError: Si no se puede conectar a la API de OpenAI
    """
    try:
        # Validar formato primero
        if not re.match(r'^sk-[A-Za-z0-9]{48}$', api_key):
            raise InvalidAPIKeyFormat(f"Formato inválido: {api_key[:10]}...")
        
        # Validar con API de OpenAI
        response = openai.Model.list(api_key=api_key)
        return "valid"
        
    except openai.error.AuthenticationError:
        return "invalid"
    except openai.error.RateLimitError:
        # Re-raise para manejo en nivel superior
        raise
    except requests.exceptions.ConnectionError as e:
        raise APIConnectionError(f"No se pudo conectar a OpenAI API: {e}")
```

### 3. Logging de Excepciones

```python
import logging

logger = logging.getLogger(__name__)

def process_repository(repo_url: str) -> None:
    try:
        # Lógica de procesamiento
        pass
    except InvalidRepositoryURL as e:
        logger.warning(f"URL de repositorio inválida: {repo_url} - {e}")
        return
    except GitHubRateLimitError as e:
        logger.error(f"Rate limit alcanzado para {repo_url}: {e}")
        raise  # Re-raise para manejo en nivel superior
    except Exception as e:
        logger.exception(f"Error inesperado procesando {repo_url}")
        raise
```

## Estándares de Testing

### 1. Estructura de Tests

```python
import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os

class TestDatabaseManager(unittest.TestCase):
    """Tests para la clase DatabaseManager."""
    
    def setUp(self):
        """Configuración antes de cada test."""
        self.temp_db_file = tempfile.NamedTemporaryFile(delete=False)
        self.db_path = self.temp_db_file.name
        self.temp_db_file.close()
        
    def tearDown(self):
        """Limpieza después de cada test."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
    
    def test_insert_valid_api_key(self):
        """Test inserción de clave API válida."""
        with DatabaseManager(self.db_path) as db:
            db.insert("sk-test123", "valid")
            self.assertTrue(db.key_exists("sk-test123"))
    
    def test_key_exists_returns_false_for_nonexistent_key(self):
        """Test que key_exists retorna False para claves inexistentes."""
        with DatabaseManager(self.db_path) as db:
            self.assertFalse(db.key_exists("sk-nonexistent"))
```

### 2. Mocking de Dependencias Externas

```python
class TestAPIKeyValidator(unittest.TestCase):
    
    @patch('openai.Model.list')
    def test_validate_api_key_success(self, mock_openai):
        """Test validación exitosa de clave API."""
        mock_openai.return_value = {"data": []}
        
        result = validate_api_key("sk-valid123")
        
        self.assertEqual(result, "valid")
        mock_openai.assert_called_once()
    
    @patch('selenium.webdriver.Chrome')
    def test_github_scanner_initialization(self, mock_driver):
        """Test inicialización del scanner de GitHub."""
        mock_driver_instance = Mock()
        mock_driver.return_value = mock_driver_instance
        
        scanner = GitHubScanner()
        
        self.assertIsNotNone(scanner.driver)
        mock_driver.assert_called_once()
```

### 3. Tests de Integración

```python
class TestIntegration(unittest.TestCase):
    """Tests de integración entre componentes."""
    
    def test_full_workflow_with_valid_key(self):
        """Test del flujo completo con clave válida."""
        with tempfile.NamedTemporaryFile() as temp_db:
            # Setup
            db_manager = DatabaseManager(temp_db.name)
            scanner = GitHubScanner()
            
            # Test workflow completo
            with db_manager:
                # Simular encontrar clave
                api_key = "sk-test123"
                status = validate_api_key(api_key)
                db_manager.insert(api_key, status)
                
                # Verificar almacenamiento
                self.assertTrue(db_manager.key_exists(api_key))
                stored_keys = db_manager.all_keys()
                self.assertIn(api_key, stored_keys)
```

## Estándares de Logging

### 1. Configuración de Logging

```python
import logging
from rich.logging import RichHandler

def setup_logging(level: str = "INFO") -> None:
    """Configura el sistema de logging del proyecto."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            RichHandler(rich_tracebacks=True),
            logging.FileHandler("scanner.log")
        ]
    )
```

### 2. Uso Consistente de Loggers

```python
import logging

# Un logger por módulo
logger = logging.getLogger(__name__)

class DatabaseManager:
    def insert(self, api_key: str, status: str) -> None:
        logger.debug(f"Insertando clave con estado: {status}")
        try:
            # Lógica de inserción
            logger.info(f"Clave insertada exitosamente")
        except Exception as e:
            logger.error(f"Error insertando clave: {e}")
            raise
```

### 3. Niveles de Log Apropiados

- **DEBUG**: Información detallada para debugging
- **INFO**: Información general del flujo de ejecución
- **WARNING**: Situaciones inesperadas pero manejables
- **ERROR**: Errores que impiden operación específica
- **CRITICAL**: Errores que impiden funcionamiento del programa

Estos estándares deben ser seguidos rigurosamente para mantener la consistencia y calidad del código en todo el proyecto.