# Seguridad y Consideraciones Éticas

## Principios Éticos Fundamentales

### 1. Uso Exclusivamente para Investigación de Seguridad

**ChatGPT-API-Scanner es una herramienta de investigación de seguridad** diseñada para:

- **Investigación académica**: Estudios sobre exposición de credenciales en repositorios públicos
- **Educación en seguridad**: Demostrar riesgos de filtración de claves API
- **Auditorías de seguridad**: Ayudar a organizaciones a identificar exposiciones accidentales
- **Concienciación**: Mostrar la importancia del manejo adecuado de credenciales

### 2. Prohibiciones Estrictas

**NUNCA usar esta herramienta para**:
- Acceso no autorizado a cuentas de terceros
- Uso comercial de claves API ajenas
- Actividades maliciosas o ilegales
- Violación de términos de servicio de GitHub u OpenAI
- Acoso o targeting de usuarios específicos

### 3. Responsabilidad del Usuario

Todo usuario de esta herramienta debe:
- Cumplir con las leyes locales e internacionales
- Respetar los términos de servicio de las plataformas
- Usar la herramienta únicamente para propósitos legítimos
- Reportar vulnerabilidades de manera responsable
- Proteger cualquier información sensible encontrada

## Implementación de Seguridad

### 1. Protección de Datos Sensibles

**Manejo de Claves API**:
```python
import hashlib
import logging

class SecureAPIKeyHandler:
    """Manejo seguro de claves API encontradas."""
    
    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """
        Genera hash de clave API para logging seguro.
        
        Args:
            api_key: Clave API completa
            
        Returns:
            Hash SHA-256 de la clave para identificación segura
        """
        return hashlib.sha256(api_key.encode()).hexdigest()[:16]
    
    @staticmethod
    def mask_api_key(api_key: str) -> str:
        """
        Enmascara clave API para logging.
        
        Args:
            api_key: Clave API completa
            
        Returns:
            Clave enmascarada (ej: "sk-****...****")
        """
        if len(api_key) < 10:
            return "****"
        return f"{api_key[:3]}****...****{api_key[-4:]}"

# Uso en logging
logger = logging.getLogger(__name__)

def log_api_key_found(api_key: str, repo_url: str):
    """Log seguro de clave API encontrada."""
    masked_key = SecureAPIKeyHandler.mask_api_key(api_key)
    key_hash = SecureAPIKeyHandler.hash_api_key(api_key)
    
    logger.info(f"Clave API encontrada: {masked_key} (hash: {key_hash}) en {repo_url}")
```

**Almacenamiento Seguro en Base de Datos**:
```python
import sqlite3
from cryptography.fernet import Fernet
import os

class SecureDatabaseManager:
    """Gestor de base de datos con encriptación."""
    
    def __init__(self, db_filename: str):
        self.db_filename = db_filename
        self.encryption_key = self._get_or_create_encryption_key()
        self.cipher = Fernet(self.encryption_key)
    
    def _get_or_create_encryption_key(self) -> bytes:
        """Obtiene o crea clave de encriptación."""
        key_file = f"{self.db_filename}.key"
        
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            # Guardar con permisos restrictivos
            with open(key_file, 'wb') as f:
                f.write(key)
            os.chmod(key_file, 0o600)  # Solo lectura/escritura para propietario
            return key
    
    def insert_encrypted(self, api_key: str, status: str) -> None:
        """Inserta clave API encriptada."""
        encrypted_key = self.cipher.encrypt(api_key.encode())
        # Almacenar solo la clave encriptada
        # Nunca almacenar la clave en texto plano
```

### 2. Protección de Cookies y Sesiones

**Manejo Seguro de Cookies de GitHub**:
```python
import json
import os
from cryptography.fernet import Fernet
from typing import Dict, Any

class SecureCookieManager:
    """Gestor seguro de cookies de GitHub."""
    
    def __init__(self, driver):
        self.driver = driver
        self.cookie_file = "github_cookies.encrypted"
        self.key_file = "cookie_encryption.key"
        self.cipher = self._get_cipher()
    
    def _get_cipher(self) -> Fernet:
        """Obtiene cipher para encriptación de cookies."""
        if os.path.exists(self.key_file):
            with open(self.key_file, 'rb') as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            os.chmod(self.key_file, 0o600)
        
        return Fernet(key)
    
    def save_secure(self) -> None:
        """Guarda cookies de forma segura y encriptada."""
        cookies = self.driver.get_cookies()
        
        # Filtrar cookies sensibles
        safe_cookies = []
        sensitive_names = ['session_token', 'auth_token', 'user_session']
        
        for cookie in cookies:
            if cookie.get('name') not in sensitive_names:
                safe_cookies.append(cookie)
        
        # Encriptar y guardar
        cookie_data = json.dumps(safe_cookies).encode()
        encrypted_data = self.cipher.encrypt(cookie_data)
        
        with open(self.cookie_file, 'wb') as f:
            f.write(encrypted_data)
        
        # Permisos restrictivos
        os.chmod(self.cookie_file, 0o600)
    
    def load_secure(self) -> None:
        """Carga cookies de forma segura."""
        if not os.path.exists(self.cookie_file):
            return
        
        try:
            with open(self.cookie_file, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data = self.cipher.decrypt(encrypted_data)
            cookies = json.loads(decrypted_data.decode())
            
            for cookie in cookies:
                self.driver.add_cookie(cookie)
                
        except Exception as e:
            logging.warning(f"No se pudieron cargar cookies: {e}")
            # Eliminar archivo corrupto
            os.remove(self.cookie_file)
```

### 3. Rate Limiting y Respeto a APIs

**Implementación de Rate Limiting Ético**:
```python
import time
from datetime import datetime, timedelta
from typing import Dict, Optional
import threading

class EthicalRateLimiter:
    """Rate limiter ético para APIs externas."""
    
    def __init__(self):
        self.github_last_request: Optional[datetime] = None
        self.openai_requests: Dict[str, list] = {}
        self.lock = threading.Lock()
        
        # Límites conservadores (más restrictivos que los oficiales)
        self.GITHUB_MIN_DELAY = 2.0  # 2 segundos entre requests
        self.OPENAI_REQUESTS_PER_MINUTE = 20  # Muy conservador
        self.OPENAI_REQUESTS_PER_HOUR = 500   # Límite horario
    
    def wait_for_github(self) -> None:
        """Espera apropiada antes de request a GitHub."""
        with self.lock:
            if self.github_last_request:
                elapsed = (datetime.now() - self.github_last_request).total_seconds()
                if elapsed < self.GITHUB_MIN_DELAY:
                    sleep_time = self.GITHUB_MIN_DELAY - elapsed
                    time.sleep(sleep_time)
            
            self.github_last_request = datetime.now()
    
    def wait_for_openai(self, api_key_hash: str) -> bool:
        """
        Verifica y espera para request a OpenAI API.
        
        Returns:
            bool: True si se puede hacer el request, False si se alcanzó el límite
        """
        with self.lock:
            now = datetime.now()
            
            if api_key_hash not in self.openai_requests:
                self.openai_requests[api_key_hash] = []
            
            requests = self.openai_requests[api_key_hash]
            
            # Limpiar requests antiguos (más de 1 hora)
            requests[:] = [req_time for req_time in requests 
                          if now - req_time < timedelta(hours=1)]
            
            # Verificar límite horario
            if len(requests) >= self.OPENAI_REQUESTS_PER_HOUR:
                return False
            
            # Verificar límite por minuto
            recent_requests = [req_time for req_time in requests 
                             if now - req_time < timedelta(minutes=1)]
            
            if len(recent_requests) >= self.OPENAI_REQUESTS_PER_MINUTE:
                # Esperar hasta que se pueda hacer el request
                oldest_recent = min(recent_requests)
                wait_until = oldest_recent + timedelta(minutes=1)
                sleep_time = (wait_until - now).total_seconds()
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
            
            # Registrar el request
            requests.append(now)
            return True

# Uso global del rate limiter
rate_limiter = EthicalRateLimiter()

def make_github_request(url: str):
    """Hace request a GitHub respetando rate limits."""
    rate_limiter.wait_for_github()
    # Hacer el request...

def validate_openai_key(api_key: str) -> str:
    """Valida clave OpenAI respetando rate limits."""
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    
    if not rate_limiter.wait_for_openai(key_hash):
        return "rate_limited"
    
    # Proceder con validación...
```

## Consideraciones Legales y de Compliance

### 1. Cumplimiento de GDPR y Privacidad

**Principios de Minimización de Datos**:
```python
class PrivacyCompliantScanner:
    """Scanner que cumple con principios de privacidad."""
    
    def __init__(self):
        self.data_retention_days = 30  # Retener datos máximo 30 días
        self.anonymize_data = True     # Anonimizar datos por defecto
    
    def process_repository(self, repo_url: str) -> None:
        """Procesa repositorio cumpliendo con privacidad."""
        # Solo extraer información necesaria
        # No almacenar información personal de usuarios
        # Anonimizar URLs y metadatos
        
        anonymized_url = self._anonymize_url(repo_url)
        logging.info(f"Procesando repositorio: {anonymized_url}")
    
    def _anonymize_url(self, url: str) -> str:
        """Anonimiza URL para logging."""
        # Remover información identificable del usuario
        # Mantener solo información necesaria para debugging
        import re
        return re.sub(r'github\.com/([^/]+)', 'github.com/[USER]', url)
    
    def cleanup_old_data(self) -> None:
        """Limpia datos antiguos según política de retención."""
        cutoff_date = datetime.now() - timedelta(days=self.data_retention_days)
        # Implementar limpieza de datos antiguos
```

### 2. Términos de Servicio y Fair Use

**Respeto a Términos de Servicio**:
```python
class ComplianceChecker:
    """Verificador de cumplimiento de términos de servicio."""
    
    @staticmethod
    def check_github_compliance() -> bool:
        """Verifica cumplimiento con términos de GitHub."""
        # Verificar que el uso sea para investigación
        # Verificar rate limits apropiados
        # Verificar que no se violen términos de servicio
        return True
    
    @staticmethod
    def check_openai_compliance() -> bool:
        """Verifica cumplimiento con términos de OpenAI."""
        # Verificar uso apropiado de API
        # No usar claves de terceros para propósitos comerciales
        # Respetar límites de uso
        return True
    
    def audit_usage(self) -> Dict[str, Any]:
        """Audita el uso de la herramienta."""
        return {
            "github_requests_last_hour": self._count_github_requests(),
            "openai_validations_last_hour": self._count_openai_requests(),
            "compliance_status": "compliant",
            "last_audit": datetime.now().isoformat()
        }
```

### 3. Divulgación Responsable

**Protocolo para Hallazgos de Seguridad**:
```python
class ResponsibleDisclosure:
    """Manejo de divulgación responsable de vulnerabilidades."""
    
    def __init__(self):
        self.disclosure_template = """
        DIVULGACIÓN RESPONSABLE DE SEGURIDAD
        
        Fecha: {date}
        Repositorio: {repo_url}
        Tipo de vulnerabilidad: Exposición de clave API
        Severidad: {severity}
        
        Descripción:
        Se encontró una clave API de OpenAI expuesta en el repositorio público.
        
        Recomendaciones:
        1. Revocar inmediatamente la clave API expuesta
        2. Generar nueva clave API
        3. Revisar historial de commits para eliminar la clave
        4. Implementar pre-commit hooks para prevenir futuras exposiciones
        
        Contacto: [Información de contacto del investigador]
        """
    
    def create_disclosure_report(self, repo_url: str, api_key_hash: str) -> str:
        """Crea reporte de divulgación responsable."""
        severity = self._assess_severity(api_key_hash)
        
        return self.disclosure_template.format(
            date=datetime.now().strftime("%Y-%m-%d"),
            repo_url=repo_url,
            severity=severity
        )
    
    def _assess_severity(self, api_key_hash: str) -> str:
        """Evalúa severidad de la exposición."""
        # Lógica para determinar severidad basada en:
        # - Antigüedad de la exposición
        # - Popularidad del repositorio
        # - Tipo de clave API
        return "HIGH"  # Por defecto, alta severidad
```

## Monitoreo y Auditoría

### 1. Logging de Actividades de Seguridad

```python
import logging
from datetime import datetime
from typing import Dict, Any

class SecurityAuditLogger:
    """Logger especializado para auditoría de seguridad."""
    
    def __init__(self):
        self.security_logger = logging.getLogger('security_audit')
        handler = logging.FileHandler('security_audit.log')
        formatter = logging.Formatter(
            '%(asctime)s - SECURITY - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.security_logger.addHandler(handler)
        self.security_logger.setLevel(logging.INFO)
    
    def log_api_key_found(self, repo_url: str, key_hash: str) -> None:
        """Log de clave API encontrada."""
        self.security_logger.warning(
            f"API_KEY_FOUND - Repo: {repo_url} - KeyHash: {key_hash}"
        )
    
    def log_validation_attempt(self, key_hash: str, result: str) -> None:
        """Log de intento de validación."""
        self.security_logger.info(
            f"VALIDATION_ATTEMPT - KeyHash: {key_hash} - Result: {result}"
        )
    
    def log_rate_limit_hit(self, service: str, limit_type: str) -> None:
        """Log de rate limit alcanzado."""
        self.security_logger.warning(
            f"RATE_LIMIT_HIT - Service: {service} - Type: {limit_type}"
        )
    
    def log_compliance_check(self, check_type: str, result: bool) -> None:
        """Log de verificación de cumplimiento."""
        self.security_logger.info(
            f"COMPLIANCE_CHECK - Type: {check_type} - Passed: {result}"
        )
```

### 2. Métricas de Uso Ético

```python
class EthicalUsageMetrics:
    """Métricas para monitorear uso ético de la herramienta."""
    
    def __init__(self):
        self.metrics = {
            "total_repositories_scanned": 0,
            "api_keys_found": 0,
            "api_keys_validated": 0,
            "rate_limits_respected": 0,
            "compliance_violations": 0,
            "session_start_time": datetime.now()
        }
    
    def increment_metric(self, metric_name: str, value: int = 1) -> None:
        """Incrementa métrica específica."""
        if metric_name in self.metrics:
            self.metrics[metric_name] += value
    
    def get_usage_report(self) -> Dict[str, Any]:
        """Genera reporte de uso."""
        session_duration = datetime.now() - self.metrics["session_start_time"]
        
        return {
            **self.metrics,
            "session_duration_minutes": session_duration.total_seconds() / 60,
            "average_repos_per_minute": self.metrics["total_repositories_scanned"] / max(1, session_duration.total_seconds() / 60),
            "ethical_compliance_score": self._calculate_compliance_score()
        }
    
    def _calculate_compliance_score(self) -> float:
        """Calcula score de cumplimiento ético."""
        total_actions = sum([
            self.metrics["total_repositories_scanned"],
            self.metrics["api_keys_validated"],
            self.metrics["rate_limits_respected"]
        ])
        
        if total_actions == 0:
            return 1.0
        
        violations = self.metrics["compliance_violations"]
        return max(0.0, 1.0 - (violations / total_actions))

# Instancia global de métricas
usage_metrics = EthicalUsageMetrics()
```

## Configuración de Seguridad por Defecto

### 1. Configuraciones Seguras por Defecto

```python
# configs.py - Configuraciones de seguridad
SECURITY_CONFIG = {
    # Encriptación
    "ENCRYPT_DATABASE": True,
    "ENCRYPT_COOKIES": True,
    "ENCRYPTION_ALGORITHM": "Fernet",
    
    # Rate Limiting
    "GITHUB_MIN_DELAY_SECONDS": 2.0,
    "OPENAI_MAX_REQUESTS_PER_MINUTE": 20,
    "OPENAI_MAX_REQUESTS_PER_HOUR": 500,
    
    # Retención de Datos
    "DATA_RETENTION_DAYS": 30,
    "AUTO_CLEANUP_ENABLED": True,
    "ANONYMIZE_LOGS": True,
    
    # Auditoría
    "ENABLE_SECURITY_LOGGING": True,
    "ENABLE_USAGE_METRICS": True,
    "COMPLIANCE_CHECKS_ENABLED": True,
    
    # Divulgación Responsable
    "AUTO_GENERATE_DISCLOSURE_REPORTS": True,
    "CONTACT_EMAIL": "security@example.com"
}
```

Estas implementaciones de seguridad y consideraciones éticas deben ser seguidas estrictamente para garantizar el uso responsable y legal de la herramienta ChatGPT-API-Scanner.