# Análisis de Rate Limits: Sistema Actual vs GitHub API

## Rate Limits del Sistema Actual

### 🐌 **Configuración Actual (Muy Conservadora)**

#### 1. GitHub Web Scraping (Selenium)
```python
# Rate limiting actual en main.py
if self.driver.find_elements(by=By.XPATH, value="//*[contains(text(), 'You have exceeded a secondary rate limit')]"):
    for _ in tqdm(range(30), desc="⏳ Rate limit reached, waiting ..."):
        time.sleep(1)  # Espera 30 segundos fijos
```

**Problemas identificados:**
- ❌ **Reactivo**: Solo responde DESPUÉS de ser rate limited
- ❌ **Fijo**: Siempre espera 30 segundos, sin adaptación
- ❌ **Ineficiente**: No aprovecha burst capacity
- ❌ **Sin predicción**: No previene rate limits

#### 2. OpenAI API Validation
```python
# Validación de claves API
with ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(check_key, unique_keys))
```

**Configuración actual:**
- ✅ **Concurrencia**: 10 workers simultáneos
- ❌ **Sin rate limiting propio**: Depende de excepciones de OpenAI
- ❌ **Sin backoff**: No maneja rate limits inteligentemente

#### 3. Delays Adicionales
```python
time.sleep(3)  # Espera fija para carga de página
time.sleep(0.05)  # Delay para tqdm progress bar
```

## 📊 **Rate Limits Oficiales de GitHub**

### GitHub Web Interface (Scraping Actual)
- **Límite**: ~10-20 requests/minuto por IP
- **Detección**: Muy agresiva, bloquea rápidamente
- **Recuperación**: 30-60 minutos de bloqueo
- **Tipo**: Rate limiting secundario (más restrictivo)

### GitHub REST API v3/v4
- **Autenticado**: 5,000 requests/hora
- **No autenticado**: 60 requests/hora
- **Search API**: 30 requests/minuto (autenticado)
- **Burst**: Permite ráfagas cortas hasta el límite

### GitHub GraphQL API v4
- **Límite**: 5,000 puntos/hora
- **Cálculo**: Basado en complejidad de query
- **Ventaja**: Una query puede obtener datos equivalentes a múltiples REST calls
- **Search**: ~10-50 puntos por query (dependiendo de complejidad)

## 🚀 **Comparación de Throughput**

### Sistema Actual (Selenium)
```
Método: Web scraping
Rate limit: ~10-20 requests/minuto
Throughput real: ~5-10 búsquedas/minuto
Tiempo por búsqueda: 30-60 segundos
Concurrencia: 1 (secuencial)
```

### GitHub REST API (Propuesto)
```
Método: REST API autenticado
Rate limit: 30 requests/minuto (search)
Throughput potencial: ~25-30 búsquedas/minuto
Tiempo por búsqueda: 2-5 segundos
Concurrencia: Hasta 30 simultáneas
```

### GitHub GraphQL API (Óptimo)
```
Método: GraphQL API
Rate limit: 5,000 puntos/hora (~100-500 queries/hora)
Throughput potencial: ~100-500 búsquedas/hora
Tiempo por búsqueda: 1-3 segundos
Concurrencia: Hasta 50-100 simultáneas
Ventaja: Datos más ricos en una sola query
```

## 🔍 **Análisis de Búsquedas Actuales**

### Tipos de Búsquedas Generadas

El sistema actual genera estas URLs de búsqueda:

#### 1. Por Patrones de Regex + Paths
```
https://github.com/search?q=(/sk-proj-[A-Za-z0-9-_]{74}T3BlbkFJ[A-Za-z0-9-_]{73}A/)+AND+(path:.xml OR path:.json OR ...)&type=code
```

#### 2. Por Patrones de Regex + Lenguajes
```
https://github.com/search?q=(/sk-proj-[A-Za-z0-9-_]{74}T3BlbkFJ[A-Za-z0-9-_]{73}A/)+language:Python&type=code
```

### Volumen Total de Búsquedas

**Cálculo actual:**
- **5 patrones de regex** × **3 grupos de paths** = 15 búsquedas
- **5 patrones de regex** × **13 lenguajes** = 65 búsquedas  
- **Total**: ~80 búsquedas por ejecución completa

**Tiempo estimado actual:**
- 80 búsquedas × 30-60 segundos = **40-80 minutos por ejecución completa**

## 💡 **Oportunidades de Optimización**

### 1. Migración a GitHub API

#### GraphQL Query Optimizada
```graphql
query SearchAPIKeys($query: String!, $first: Int!, $after: String) {
  search(query: $query, type: REPOSITORY, first: $first, after: $after) {
    repositoryCount
    edges {
      node {
        ... on Repository {
          name
          owner { login }
          defaultBranchRef {
            target {
              ... on Commit {
                tree {
                  entries {
                    name
                    type
                    object {
                      ... on Blob {
                        text
                        byteSize
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
```

**Ventajas:**
- ✅ Una query obtiene repo + archivos + contenido
- ✅ Paginación eficiente con cursors
- ✅ Rate limiting predecible
- ✅ Datos estructurados (JSON)

### 2. Rate Limiting Inteligente

#### Implementación Propuesta
```python
class GitHubRateLimiter:
    def __init__(self):
        # GitHub Search API: 30 requests/minute
        self.search_limit = 30
        self.search_window = 60  # seconds
        self.search_requests = deque()
        
        # GitHub GraphQL: 5000 points/hour
        self.graphql_limit = 5000
        self.graphql_window = 3600  # seconds
        self.graphql_points_used = 0
        
    async def acquire_search_token(self):
        """Acquire token for search API with intelligent waiting."""
        now = time.time()
        
        # Remove old requests outside window
        while self.search_requests and now - self.search_requests[0] > self.search_window:
            self.search_requests.popleft()
        
        # Check if we need to wait
        if len(self.search_requests) >= self.search_limit:
            wait_time = self.search_window - (now - self.search_requests[0])
            await asyncio.sleep(wait_time)
        
        self.search_requests.append(now)
        return True
    
    async def acquire_graphql_token(self, estimated_cost: int = 1):
        """Acquire token for GraphQL API with cost estimation."""
        if self.graphql_points_used + estimated_cost > self.graphql_limit:
            # Wait until next hour or implement sliding window
            wait_time = self._calculate_graphql_wait_time()
            await asyncio.sleep(wait_time)
            self.graphql_points_used = 0
        
        self.graphql_points_used += estimated_cost
        return True
```

### 3. Optimización de Consultas

#### Consultas Combinadas Inteligentes
```python
# En lugar de 80 búsquedas separadas, usar consultas combinadas
optimized_queries = [
    # Combinar múltiples patrones en una query
    "(/sk-proj-[A-Za-z0-9-_]{74}/ OR /sk-[a-zA-Z0-9]{48}/) language:Python",
    "(/sk-proj-[A-Za-z0-9-_]{74}/ OR /sk-[a-zA-Z0-9]{48}/) language:JavaScript",
    # Combinar paths comunes
    "sk-proj- (path:*.env OR path:*.config OR path:*.json)",
]
```

**Reducción esperada:**
- De **80 búsquedas** a **15-20 búsquedas optimizadas**
- De **40-80 minutos** a **5-10 minutos**

## 📈 **Mejoras de Performance Esperadas**

### Comparación de Throughput

| Método | Requests/min | Tiempo Total | Mejora |
|--------|-------------|--------------|--------|
| **Actual (Selenium)** | 0.5-1 | 40-80 min | Baseline |
| **REST API** | 25-30 | 3-5 min | **8-15x** |
| **GraphQL API** | 50-100 | 1-3 min | **15-40x** |
| **GraphQL + Optimización** | 100-200 | 0.5-1 min | **40-80x** |

### Rate Limiting Inteligente vs Actual

| Aspecto | Sistema Actual | Sistema Optimizado |
|---------|---------------|-------------------|
| **Detección** | Reactiva (después del bloqueo) | Predictiva (antes del límite) |
| **Espera** | Fija (30s siempre) | Adaptativa (0.1-30s según necesidad) |
| **Recuperación** | Manual refresh | Automática con backoff exponencial |
| **Utilización** | ~20% del límite disponible | ~90% del límite disponible |

## 🎯 **Recomendaciones Inmediatas**

### Fase 1: Quick Wins (1-2 semanas)
1. **Implementar GitHub REST API** para reemplazar Selenium
2. **Rate limiting predictivo** en lugar de reactivo
3. **Consultas combinadas** para reducir número total

### Fase 2: Optimización Avanzada (2-4 semanas)
1. **Migrar a GraphQL API** para máximo rendimiento
2. **Cache inteligente** para evitar re-búsquedas
3. **Procesamiento asíncrono** masivo

### Fase 3: Optimización Extrema (4-6 semanas)
1. **Machine learning** para optimizar consultas
2. **Distributed workers** para paralelización
3. **Predictive caching** basado en patrones

**Resultado esperado: De 40-80 minutos a 30 segundos - 2 minutos por ejecución completa.**