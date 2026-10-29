import time
from typing import List, Dict, Any

class KPITracker:
    def __init__(self):
        self.resolution_times: List[float] = []      # seconds
        self.translation_latencies: List[float] = [] # milliseconds
        self.total_exceptions: int = 0
        self.resolved_exceptions: int = 0
        self.escalated_exceptions: int = 0
        self.total_cost: float = 0.0                # INR estimated cost
        
    def record_exception_created(self):
        self.total_exceptions += 1

    def record_resolution(self, duration_seconds: float, success: bool = True):
        if success:
            self.resolved_exceptions += 1
            self.resolution_times.append(duration_seconds)
            # Estimate cost: approx ₹1.80 per resolved exception (telephony + LLM)
            self.total_cost += 1.80
        else:
            self.escalated_exceptions += 1
            # Still incurred voice / SMS cost: approx ₹0.90
            self.total_cost += 0.90

    def record_translation_turn(self, latency_ms: float):
        self.translation_latencies.append(latency_ms)

    def get_kpis(self) -> Dict[str, Any]:
        avg_res = sum(self.resolution_times) / len(self.resolution_times) if self.resolution_times else 0.0
        avg_lat = sum(self.translation_latencies) / len(self.translation_latencies) if self.translation_latencies else 0.0
        success_rate = (self.resolved_exceptions / self.total_exceptions * 100.0) if self.total_exceptions > 0 else 100.0
        cost_per_exc = (self.total_cost / self.total_exceptions) if self.total_exceptions > 0 else 0.0
        
        return {
            "avg_resolution_seconds": round(avg_res, 1),
            "avg_translation_latency_ms": round(avg_lat, 1),
            "success_rate": round(success_rate, 1),
            "cost_per_exception": round(cost_per_exc, 2),
            "total_exceptions": self.total_exceptions,
            "resolved_exceptions": self.resolved_exceptions,
            "escalated_exceptions": self.escalated_exceptions
        }

kpi_tracker = KPITracker()
