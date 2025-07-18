"""
Real-time metrics collection and analysis.

This module provides comprehensive metrics collection for monitoring
system performance, API usage, and operational statistics.
"""

import asyncio
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import deque, defaultdict
from dataclasses import dataclass, field
import statistics

from ..async_core.base import AsyncContextManager


@dataclass
class MetricPoint:
    """Individual metric data point."""
    timestamp: datetime
    value: float
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricSummary:
    """Summary statistics for a metric."""
    count: int
    sum: float
    min: float
    max: float
    mean: float
    median: float
    p95: float
    p99: float


class MetricsCollector(AsyncContextManager):
    """
    Real-time metrics collector with statistical analysis.
    
    Collects and analyzes performance metrics including latency,
    throughput, error rates, and custom application metrics.
    """
    
    def __init__(self, max_points_per_metric: int = 10000) -> None:
        """
        Initialize metrics collector.
        
        Args:
            max_points_per_metric: Maximum data points to keep per metric
        """
        super().__init__()
        self.max_points_per_metric = max_points_per_metric
        
        # Metric storage
        self.metrics: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_points_per_metric)
        )
        
        # Counters for discrete events
        self.counters: Dict[str, int] = defaultdict(int)
        
        # Gauges for current values
        self.gauges: Dict[str, float] = {}
        
        # Histograms for distribution analysis
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        # Background task for cleanup
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def _async_init(self) -> None:
        """Initialize metrics collector."""
        # Start background cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_old_metrics())
        self.logger.info("Metrics collector initialized")
    
    async def _async_close(self) -> None:
        """Close metrics collector."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Metrics collector closed")
    
    async def record_metric(
        self, 
        name: str, 
        value: float, 
        tags: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Record a metric value.
        
        Args:
            name: Metric name
            value: Metric value
            tags: Optional tags for the metric
        """
        async with self._lock:
            point = MetricPoint(
                timestamp=datetime.now(),
                value=value,
                tags=tags or {}
            )
            self.metrics[name].append(point)
    
    async def increment_counter(self, name: str, value: int = 1) -> None:
        """
        Increment a counter metric.
        
        Args:
            name: Counter name
            value: Increment value (default 1)
        """
        async with self._lock:
            self.counters[name] += value
    
    async def set_gauge(self, name: str, value: float) -> None:
        """
        Set a gauge metric value.
        
        Args:
            name: Gauge name
            value: Current value
        """
        async with self._lock:
            self.gauges[name] = value
    
    async def record_histogram(self, name: str, value: float) -> None:
        """
        Record a value in a histogram.
        
        Args:
            name: Histogram name
            value: Value to record
        """
        async with self._lock:
            self.histograms[name].append(value)
            
            # Keep histogram size manageable
            if len(self.histograms[name]) > self.max_points_per_metric:
                self.histograms[name] = self.histograms[name][-self.max_points_per_metric:]
    
    async def get_metric_summary(
        self, 
        name: str, 
        time_window: Optional[timedelta] = None
    ) -> Optional[MetricSummary]:
        """
        Get summary statistics for a metric.
        
        Args:
            name: Metric name
            time_window: Time window to analyze (None for all data)
            
        Returns:
            Optional[MetricSummary]: Summary statistics or None if no data
        """
        async with self._lock:
            if name not in self.metrics:
                return None
            
            points = list(self.metrics[name])
            
            # Filter by time window if specified
            if time_window:
                cutoff_time = datetime.now() - time_window
                points = [p for p in points if p.timestamp >= cutoff_time]
            
            if not points:
                return None
            
            values = [p.value for p in points]
            
            return MetricSummary(
                count=len(values),
                sum=sum(values),
                min=min(values),
                max=max(values),
                mean=statistics.mean(values),
                median=statistics.median(values),
                p95=self._percentile(values, 0.95),
                p99=self._percentile(values, 0.99)
            )
    
    async def get_counter_value(self, name: str) -> int:
        """
        Get current counter value.
        
        Args:
            name: Counter name
            
        Returns:
            int: Current counter value
        """
        async with self._lock:
            return self.counters.get(name, 0)
    
    async def get_gauge_value(self, name: str) -> Optional[float]:
        """
        Get current gauge value.
        
        Args:
            name: Gauge name
            
        Returns:
            Optional[float]: Current gauge value or None if not set
        """
        async with self._lock:
            return self.gauges.get(name)
    
    async def get_histogram_summary(self, name: str) -> Optional[MetricSummary]:
        """
        Get histogram summary statistics.
        
        Args:
            name: Histogram name
            
        Returns:
            Optional[MetricSummary]: Summary statistics or None if no data
        """
        async with self._lock:
            if name not in self.histograms or not self.histograms[name]:
                return None
            
            values = self.histograms[name]
            
            return MetricSummary(
                count=len(values),
                sum=sum(values),
                min=min(values),
                max=max(values),
                mean=statistics.mean(values),
                median=statistics.median(values),
                p95=self._percentile(values, 0.95),
                p99=self._percentile(values, 0.99)
            )
    
    async def get_all_metrics(self) -> Dict[str, Any]:
        """
        Get all current metrics.
        
        Returns:
            Dict[str, Any]: All metrics data
        """
        async with self._lock:
            result = {
                'timestamp': datetime.now().isoformat(),
                'counters': dict(self.counters),
                'gauges': dict(self.gauges),
                'metrics': {},
                'histograms': {}
            }
            
            # Get summaries for all metrics
            for name in self.metrics:
                summary = await self.get_metric_summary(name)
                if summary:
                    result['metrics'][name] = {
                        'count': summary.count,
                        'mean': summary.mean,
                        'min': summary.min,
                        'max': summary.max,
                        'p95': summary.p95,
                        'p99': summary.p99
                    }
            
            # Get histogram summaries
            for name in self.histograms:
                summary = await self.get_histogram_summary(name)
                if summary:
                    result['histograms'][name] = {
                        'count': summary.count,
                        'mean': summary.mean,
                        'min': summary.min,
                        'max': summary.max,
                        'p95': summary.p95,
                        'p99': summary.p99
                    }
            
            return result
    
    async def reset_metrics(self) -> None:
        """Reset all metrics."""
        async with self._lock:
            self.metrics.clear()
            self.counters.clear()
            self.gauges.clear()
            self.histograms.clear()
        
        self.logger.info("All metrics reset")
    
    def _percentile(self, values: List[float], percentile: float) -> float:
        """
        Calculate percentile value.
        
        Args:
            values: List of values
            percentile: Percentile to calculate (0.0 to 1.0)
            
        Returns:
            float: Percentile value
        """
        if not values:
            return 0.0
        
        sorted_values = sorted(values)
        index = int(percentile * (len(sorted_values) - 1))
        return sorted_values[index]
    
    async def _cleanup_old_metrics(self) -> None:
        """Background task to clean up old metric data."""
        while True:
            try:
                await asyncio.sleep(5)  # Run every 5 seconds for testing
                
                cutoff_time = datetime.now() - timedelta(hours=24)
                
                async with self._lock:
                    # Clean up old metric points
                    for name, points in self.metrics.items():
                        # Remove points older than 24 hours
                        while points and points[0].timestamp < cutoff_time:
                            points.popleft()
                    
                    # Clean up empty metrics
                    empty_metrics = [name for name, points in self.metrics.items() if not points]
                    for name in empty_metrics:
                        del self.metrics[name]
                
                self.logger.debug("Cleaned up old metrics")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in metrics cleanup: {e}")


# Context manager for timing operations
class TimingContext:
    """Context manager for timing operations and recording metrics."""
    
    def __init__(self, metrics_collector: MetricsCollector, metric_name: str):
        """
        Initialize timing context.
        
        Args:
            metrics_collector: Metrics collector instance
            metric_name: Name of the metric to record
        """
        self.metrics_collector = metrics_collector
        self.metric_name = metric_name
        self.start_time: Optional[float] = None
    
    async def __aenter__(self):
        """Start timing."""
        self.start_time = time.time()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """End timing and record metric."""
        if self.start_time is not None:
            duration = time.time() - self.start_time
            await self.metrics_collector.record_metric(self.metric_name, duration)
            
            # Also record in histogram for distribution analysis
            await self.metrics_collector.record_histogram(
                f"{self.metric_name}_histogram", 
                duration
            )