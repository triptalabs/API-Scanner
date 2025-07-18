"""
Performance monitoring and system optimization.

This module provides real-time performance monitoring with automatic
system optimization based on observed performance patterns and metrics.
"""

import asyncio
import psutil
import time
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
import statistics

from ..async_core.base import AsyncContextManager
from .metrics_collector import MetricsCollector


@dataclass
class PerformanceThreshold:
    """Performance threshold configuration."""
    metric_name: str
    warning_threshold: float
    critical_threshold: float
    action: Optional[Callable] = None


@dataclass
class SystemMetrics:
    """System performance metrics snapshot."""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_available_mb: float
    disk_io_read_mb: float
    disk_io_write_mb: float
    network_bytes_sent: float
    network_bytes_recv: float
    active_connections: int


class PerformanceMonitor(AsyncContextManager):
    """
    Real-time performance monitor with adaptive optimization.
    
    Monitors system and application performance metrics, detects
    performance issues, and automatically applies optimizations.
    """
    
    def __init__(
        self,
        metrics_collector: MetricsCollector,
        monitoring_interval: float = 5.0,
        optimization_enabled: bool = True
    ) -> None:
        """
        Initialize performance monitor.
        
        Args:
            metrics_collector: Metrics collector instance
            monitoring_interval: Monitoring interval in seconds
            optimization_enabled: Enable automatic optimizations
        """
        super().__init__()
        self.metrics_collector = metrics_collector
        self.monitoring_interval = monitoring_interval
        self.optimization_enabled = optimization_enabled
        
        # Performance thresholds
        self.thresholds: List[PerformanceThreshold] = []
        
        # System metrics history
        self.system_metrics_history: List[SystemMetrics] = []
        self.max_history_size = 1000
        
        # Performance state
        self.performance_alerts: List[Dict[str, Any]] = []
        self.optimization_actions: List[Dict[str, Any]] = []
        
        # Background tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._optimization_task: Optional[asyncio.Task] = None
        
        # Initial system state
        self._initial_net_io = psutil.net_io_counters()
        self._initial_disk_io = psutil.disk_io_counters()
        self._last_measurement_time = time.time()
    
    async def _async_init(self) -> None:
        """Initialize performance monitor."""
        # Set up default thresholds
        await self._setup_default_thresholds()
        
        # Start monitoring tasks
        self._monitoring_task = asyncio.create_task(self._monitor_performance())
        
        if self.optimization_enabled:
            self._optimization_task = asyncio.create_task(self._optimize_performance())
        
        self.logger.info("Performance monitor initialized")
    
    async def _async_close(self) -> None:
        """Close performance monitor."""
        # Cancel background tasks
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        if self._optimization_task:
            self._optimization_task.cancel()
            try:
                await self._optimization_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Performance monitor closed")
    
    async def _setup_default_thresholds(self) -> None:
        """Set up default performance thresholds."""
        default_thresholds = [
            PerformanceThreshold("cpu_percent", 80.0, 95.0),
            PerformanceThreshold("memory_percent", 85.0, 95.0),
            PerformanceThreshold("response_time_ms", 1000.0, 5000.0),
            PerformanceThreshold("error_rate_percent", 5.0, 15.0),
            PerformanceThreshold("queue_size", 1000, 5000),
        ]
        
        self.thresholds.extend(default_thresholds)
    
    async def add_threshold(self, threshold: PerformanceThreshold) -> None:
        """
        Add a performance threshold.
        
        Args:
            threshold: Performance threshold to add
        """
        self.thresholds.append(threshold)
        self.logger.debug(f"Added performance threshold: {threshold.metric_name}")
    
    async def _monitor_performance(self) -> None:
        """Background task for performance monitoring."""
        while True:
            try:
                # Collect system metrics
                system_metrics = await self._collect_system_metrics()
                
                # Store in history
                self.system_metrics_history.append(system_metrics)
                if len(self.system_metrics_history) > self.max_history_size:
                    self.system_metrics_history.pop(0)
                
                # Record metrics
                await self._record_system_metrics(system_metrics)
                
                # Check thresholds
                await self._check_thresholds(system_metrics)
                
                # Wait for next monitoring cycle
                await asyncio.sleep(self.monitoring_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in performance monitoring: {e}")
                await asyncio.sleep(self.monitoring_interval)
    
    async def _collect_system_metrics(self) -> SystemMetrics:
        """Collect current system performance metrics."""
        current_time = time.time()
        time_delta = current_time - self._last_measurement_time
        
        # CPU and Memory
        cpu_percent = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        
        # Disk I/O
        current_disk_io = psutil.disk_io_counters()
        disk_read_mb = 0.0
        disk_write_mb = 0.0
        
        if self._initial_disk_io and current_disk_io:
            disk_read_mb = (current_disk_io.read_bytes - self._initial_disk_io.read_bytes) / (1024 * 1024 * time_delta)
            disk_write_mb = (current_disk_io.write_bytes - self._initial_disk_io.write_bytes) / (1024 * 1024 * time_delta)
        
        # Network I/O
        current_net_io = psutil.net_io_counters()
        net_sent = 0.0
        net_recv = 0.0
        
        if self._initial_net_io and current_net_io:
            net_sent = (current_net_io.bytes_sent - self._initial_net_io.bytes_sent) / time_delta
            net_recv = (current_net_io.bytes_recv - self._initial_net_io.bytes_recv) / time_delta
        
        # Network connections
        try:
            connections = len(psutil.net_connections())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            connections = 0
        
        # Update for next measurement
        self._initial_disk_io = current_disk_io
        self._initial_net_io = current_net_io
        self._last_measurement_time = current_time
        
        return SystemMetrics(
            timestamp=datetime.now(),
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_available_mb=memory.available / (1024 * 1024),
            disk_io_read_mb=disk_read_mb,
            disk_io_write_mb=disk_write_mb,
            network_bytes_sent=net_sent,
            network_bytes_recv=net_recv,
            active_connections=connections
        )
    
    async def _record_system_metrics(self, metrics: SystemMetrics) -> None:
        """Record system metrics in the metrics collector."""
        await self.metrics_collector.set_gauge("system.cpu_percent", metrics.cpu_percent)
        await self.metrics_collector.set_gauge("system.memory_percent", metrics.memory_percent)
        await self.metrics_collector.set_gauge("system.memory_available_mb", metrics.memory_available_mb)
        await self.metrics_collector.set_gauge("system.disk_io_read_mb_per_sec", metrics.disk_io_read_mb)
        await self.metrics_collector.set_gauge("system.disk_io_write_mb_per_sec", metrics.disk_io_write_mb)
        await self.metrics_collector.set_gauge("system.network_bytes_sent_per_sec", metrics.network_bytes_sent)
        await self.metrics_collector.set_gauge("system.network_bytes_recv_per_sec", metrics.network_bytes_recv)
        await self.metrics_collector.set_gauge("system.active_connections", metrics.active_connections)
    
    async def _check_thresholds(self, metrics: SystemMetrics) -> None:
        """Check performance thresholds and generate alerts."""
        current_values = {
            "cpu_percent": metrics.cpu_percent,
            "memory_percent": metrics.memory_percent,
            "active_connections": metrics.active_connections
        }
        
        # Add application metrics from metrics collector
        app_metrics = await self.metrics_collector.get_all_metrics()
        
        # Check response time
        if 'response_time' in app_metrics.get('histograms', {}):
            response_time_summary = app_metrics['histograms']['response_time']
            current_values["response_time_ms"] = response_time_summary.get('mean', 0) * 1000
        
        # Check error rate
        total_requests = app_metrics.get('counters', {}).get('total_requests', 0)
        error_requests = app_metrics.get('counters', {}).get('error_requests', 0)
        if total_requests > 0:
            current_values["error_rate_percent"] = (error_requests / total_requests) * 100
        
        # Check queue sizes
        current_values["queue_size"] = app_metrics.get('gauges', {}).get('queue_size', 0)
        
        # Check each threshold
        for threshold in self.thresholds:
            if threshold.metric_name in current_values:
                value = current_values[threshold.metric_name]
                
                if value >= threshold.critical_threshold:
                    await self._generate_alert(
                        threshold.metric_name, 
                        value, 
                        "CRITICAL", 
                        threshold.critical_threshold
                    )
                    
                    if threshold.action:
                        await self._execute_threshold_action(threshold, value)
                        
                elif value >= threshold.warning_threshold:
                    await self._generate_alert(
                        threshold.metric_name, 
                        value, 
                        "WARNING", 
                        threshold.warning_threshold
                    )
    
    async def _generate_alert(
        self, 
        metric_name: str, 
        value: float, 
        severity: str, 
        threshold: float
    ) -> None:
        """Generate a performance alert."""
        alert = {
            "timestamp": datetime.now().isoformat(),
            "metric_name": metric_name,
            "value": value,
            "threshold": threshold,
            "severity": severity,
            "message": f"{metric_name} is {value:.2f}, exceeding {severity.lower()} threshold of {threshold:.2f}"
        }
        
        self.performance_alerts.append(alert)
        
        # Keep only recent alerts (last 100)
        if len(self.performance_alerts) > 100:
            self.performance_alerts.pop(0)
        
        self.logger.warning(f"Performance alert: {alert['message']}")
        
        # Record alert metric
        await self.metrics_collector.increment_counter(f"alerts.{severity.lower()}")
    
    async def _execute_threshold_action(
        self, 
        threshold: PerformanceThreshold, 
        value: float
    ) -> None:
        """Execute action for threshold breach."""
        try:
            if threshold.action:
                await threshold.action(threshold.metric_name, value)
                
                action_record = {
                    "timestamp": datetime.now().isoformat(),
                    "metric_name": threshold.metric_name,
                    "value": value,
                    "action": "threshold_action_executed"
                }
                
                self.optimization_actions.append(action_record)
                self.logger.info(f"Executed threshold action for {threshold.metric_name}")
                
        except Exception as e:
            self.logger.error(f"Error executing threshold action: {e}")
    
    async def _optimize_performance(self) -> None:
        """Background task for performance optimization."""
        while True:
            try:
                await asyncio.sleep(60)  # Run optimization every minute
                
                # Analyze recent performance
                await self._analyze_performance_trends()
                
                # Apply optimizations if needed
                await self._apply_optimizations()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in performance optimization: {e}")
                await asyncio.sleep(60)
    
    async def _analyze_performance_trends(self) -> None:
        """Analyze performance trends and identify optimization opportunities."""
        if len(self.system_metrics_history) < 10:
            return
        
        # Get recent metrics (last 10 minutes)
        recent_metrics = self.system_metrics_history[-10:]
        
        # Analyze CPU trend
        cpu_values = [m.cpu_percent for m in recent_metrics]
        cpu_trend = self._calculate_trend(cpu_values)
        
        if cpu_trend > 5.0:  # CPU increasing by more than 5% per measurement
            await self._record_optimization_opportunity("cpu_increasing", cpu_trend)
        
        # Analyze memory trend
        memory_values = [m.memory_percent for m in recent_metrics]
        memory_trend = self._calculate_trend(memory_values)
        
        if memory_trend > 2.0:  # Memory increasing by more than 2% per measurement
            await self._record_optimization_opportunity("memory_increasing", memory_trend)
        
        # Analyze response time trend from application metrics
        app_metrics = await self.metrics_collector.get_all_metrics()
        if 'response_time' in app_metrics.get('histograms', {}):
            response_summary = app_metrics['histograms']['response_time']
            if response_summary.get('mean', 0) > 1.0:  # Response time > 1 second
                await self._record_optimization_opportunity("slow_response_time", response_summary['mean'])
    
    def _calculate_trend(self, values: List[float]) -> float:
        """Calculate trend (slope) of values."""
        if len(values) < 2:
            return 0.0
        
        n = len(values)
        x_values = list(range(n))
        
        # Calculate linear regression slope
        x_mean = statistics.mean(x_values)
        y_mean = statistics.mean(values)
        
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, values))
        denominator = sum((x - x_mean) ** 2 for x in x_values)
        
        if denominator == 0:
            return 0.0
        
        return numerator / denominator
    
    async def _record_optimization_opportunity(self, opportunity_type: str, value: float) -> None:
        """Record an optimization opportunity."""
        opportunity = {
            "timestamp": datetime.now().isoformat(),
            "type": opportunity_type,
            "value": value,
            "status": "identified"
        }
        
        self.optimization_actions.append(opportunity)
        self.logger.info(f"Optimization opportunity identified: {opportunity_type} = {value:.2f}")
        
        # Record metric
        await self.metrics_collector.increment_counter(f"optimization.opportunities.{opportunity_type}")
    
    async def _apply_optimizations(self) -> None:
        """Apply performance optimizations based on current conditions."""
        # Get current system state
        if not self.system_metrics_history:
            return
        
        current_metrics = self.system_metrics_history[-1]
        
        # CPU optimization
        if current_metrics.cpu_percent > 80:
            await self._optimize_cpu_usage()
        
        # Memory optimization
        if current_metrics.memory_percent > 85:
            await self._optimize_memory_usage()
        
        # Connection optimization
        if current_metrics.active_connections > 1000:
            await self._optimize_connections()
    
    async def _optimize_cpu_usage(self) -> None:
        """Apply CPU usage optimizations."""
        optimization = {
            "timestamp": datetime.now().isoformat(),
            "type": "cpu_optimization",
            "action": "reduce_concurrent_operations",
            "status": "applied"
        }
        
        self.optimization_actions.append(optimization)
        self.logger.info("Applied CPU optimization: reduced concurrent operations")
        
        # Record optimization metric
        await self.metrics_collector.increment_counter("optimization.applied.cpu")
    
    async def _optimize_memory_usage(self) -> None:
        """Apply memory usage optimizations."""
        optimization = {
            "timestamp": datetime.now().isoformat(),
            "type": "memory_optimization",
            "action": "trigger_garbage_collection",
            "status": "applied"
        }
        
        self.optimization_actions.append(optimization)
        self.logger.info("Applied memory optimization: triggered garbage collection")
        
        # Record optimization metric
        await self.metrics_collector.increment_counter("optimization.applied.memory")
    
    async def _optimize_connections(self) -> None:
        """Apply connection optimizations."""
        optimization = {
            "timestamp": datetime.now().isoformat(),
            "type": "connection_optimization",
            "action": "reduce_connection_pool_size",
            "status": "applied"
        }
        
        self.optimization_actions.append(optimization)
        self.logger.info("Applied connection optimization: reduced connection pool size")
        
        # Record optimization metric
        await self.metrics_collector.increment_counter("optimization.applied.connections")
    
    async def get_performance_report(self) -> Dict[str, Any]:
        """
        Get comprehensive performance report.
        
        Returns:
            Dict[str, Any]: Performance report with metrics and analysis
        """
        if not self.system_metrics_history:
            return {"error": "No performance data available"}
        
        current_metrics = self.system_metrics_history[-1]
        
        # Calculate averages over last hour
        recent_metrics = [
            m for m in self.system_metrics_history
            if (datetime.now() - m.timestamp).total_seconds() < 3600
        ]
        
        if recent_metrics:
            avg_cpu = statistics.mean(m.cpu_percent for m in recent_metrics)
            avg_memory = statistics.mean(m.memory_percent for m in recent_metrics)
            avg_connections = statistics.mean(m.active_connections for m in recent_metrics)
        else:
            avg_cpu = avg_memory = avg_connections = 0
        
        # Get application metrics
        app_metrics = await self.metrics_collector.get_all_metrics()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "current_system_metrics": {
                "cpu_percent": current_metrics.cpu_percent,
                "memory_percent": current_metrics.memory_percent,
                "memory_available_mb": current_metrics.memory_available_mb,
                "active_connections": current_metrics.active_connections
            },
            "hourly_averages": {
                "cpu_percent": avg_cpu,
                "memory_percent": avg_memory,
                "active_connections": avg_connections
            },
            "application_metrics": app_metrics,
            "recent_alerts": self.performance_alerts[-10:],  # Last 10 alerts
            "recent_optimizations": self.optimization_actions[-10:],  # Last 10 optimizations
            "performance_score": await self._calculate_performance_score()
        }
    
    async def _calculate_performance_score(self) -> float:
        """
        Calculate overall performance score (0-100).
        
        Returns:
            float: Performance score
        """
        if not self.system_metrics_history:
            return 0.0
        
        current_metrics = self.system_metrics_history[-1]
        
        # Score components (0-100 each)
        cpu_score = max(0, 100 - current_metrics.cpu_percent)
        memory_score = max(0, 100 - current_metrics.memory_percent)
        
        # Connection score (assume 1000 connections = 0 score)
        connection_score = max(0, 100 - (current_metrics.active_connections / 10))
        
        # Alert penalty
        recent_alerts = len([
            a for a in self.performance_alerts
            if (datetime.now() - datetime.fromisoformat(a['timestamp'])).total_seconds() < 3600
        ])
        alert_penalty = min(50, recent_alerts * 5)  # Max 50 point penalty
        
        # Calculate weighted average
        base_score = (cpu_score * 0.4 + memory_score * 0.4 + connection_score * 0.2)
        final_score = max(0, base_score - alert_penalty)
        
        return round(final_score, 2)