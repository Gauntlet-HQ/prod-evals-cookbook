"""
Experiment Runner - Compare agent variants across test suites.

Runs the same evaluation suite with different agent configurations
and collects metrics for comparison.
"""

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

# Add directories to path
sys.path.insert(0, str(Path(__file__).parent.parent / "setup_agent"))
sys.path.insert(0, str(Path(__file__).parent.parent / "stage_4_rubrics"))


@dataclass
class RunResult:
    """Result from a single test case run."""
    case_id: str
    query: str
    response: str
    passed: bool
    rubric_score: Optional[float]
    latency_ms: float
    input_tokens: int
    output_tokens: int
    tools_used: list[str]
    error: Optional[str] = None


@dataclass
class VariantResults:
    """Aggregated results for a variant."""
    variant_name: str
    config: dict
    total_cases: int
    passed: int
    failed: int
    pass_rate: float
    avg_rubric_score: float
    avg_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost: float
    results: list[RunResult]


def load_variants(variants_path: str) -> dict:
    """Load variant configurations."""
    with open(variants_path) as f:
        data = yaml.safe_load(f)
    
    defaults = data.get("defaults", {})
    variants = {}
    
    for name, config in data.get("variants", {}).items():
        # Merge defaults with variant-specific config
        merged = {**defaults, **config}
        
        # Resolve prompt references
        if merged.get("system_prompt") in data.get("prompts", {}):
            merged["system_prompt_text"] = data["prompts"][merged["system_prompt"]]
        
        variants[name] = merged
    
    return variants


def load_test_cases(source: str) -> list[dict]:
    """Load test cases from specified source."""
    base_path = Path(__file__).parent.parent
    
    if source == "golden":
        path = base_path / "stage_1_golden_sets" / "golden_data.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        return data.get("test_cases", [])
    
    elif source == "scenarios":
        path = base_path / "stage_2_labeled_scenarios" / "scenarios.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        return data.get("scenarios", [])
    
    elif source == "rubrics":
        path = base_path / "stage_4_rubrics" / "rubrics.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        return data.get("test_cases", [])
    
    else:
        raise ValueError(f"Unknown test source: {source}")


def create_agent_with_config(config: dict):
    """Create an agent instance with the specified configuration."""
    from orchestrator import create_agent, DEFAULT_SYSTEM_PROMPT
    
    # Get system prompt
    system_prompt = config.get("system_prompt_text", DEFAULT_SYSTEM_PROMPT)
    
    # Create agent with config overrides
    agent = create_agent(
        model=config.get("model", "gpt-4o-mini"),
        temperature=config.get("temperature", 0.1),
        system_prompt=system_prompt
    )
    
    return agent


def run_single_case(
    agent,
    case: dict,
    config: dict,
    include_rubrics: bool = False
) -> RunResult:
    """Run a single test case and collect metrics."""
    from langchain_core.messages import HumanMessage
    
    query = case["query"]
    case_id = case.get("id", "unknown")
    
    start_time = time.time()
    error = None
    response = ""
    tools_used = []
    input_tokens = 0
    output_tokens = 0
    
    try:
        # Run the agent
        result = agent.invoke({
            "messages": [HumanMessage(content=query)]
        })
        
        # Extract response
        messages = result.get("messages", [])
        if messages:
            response = str(messages[-1].text)
        
        # Extract tool usage from messages
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tools_used.append(tc.get("name", "unknown"))
        
        # Estimate tokens (rough approximation)
        input_tokens = len(query.split()) * 1.3
        output_tokens = len(response.split()) * 1.3
        
    except Exception as e:
        error = str(e)
        response = ""
    
    latency_ms = (time.time() - start_time) * 1000
    
    # Check if passed (basic check against expected content)
    passed = True
    if "must_contain" in case:
        for phrase in case["must_contain"]:
            if phrase.lower() not in response.lower():
                passed = False
                break
    
    if "must_not_contain" in case:
        for phrase in case["must_not_contain"]:
            if phrase.lower() in response.lower():
                passed = False
                break
    
    # Score with rubrics if requested
    rubric_score = None
    if include_rubrics and not error:
        try:
            from scorer import RubricScorer
            scorer = RubricScorer()
            result = scorer.score(
                query=query,
                response=response,
                category=case.get("category")
            )
            rubric_score = result.overall_score
        except Exception:
            pass
    
    return RunResult(
        case_id=case_id,
        query=query,
        response=response[:500],  # Truncate for storage
        passed=passed,
        rubric_score=rubric_score,
        latency_ms=latency_ms,
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        tools_used=tools_used,
        error=error
    )


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Estimate API cost based on token usage."""
    # Pricing per 1M tokens (as of 2024)
    pricing = {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    }
    
    rates = pricing.get(model, pricing["gpt-4o-mini"])
    cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
    return cost


def run_variant(
    variant_name: str,
    config: dict,
    test_cases: list[dict],
    include_rubrics: bool = False,
    verbose: bool = True
) -> VariantResults:
    """Run all test cases for a single variant."""
    if verbose:
        print(f"\n{'='*60}")
        print(f"Running variant: {variant_name}")
        print(f"Config: model={config.get('model')}, temp={config.get('temperature')}")
        print(f"{'='*60}")
    
    agent = create_agent_with_config(config)
    results = []
    
    for i, case in enumerate(test_cases):
        if verbose:
            print(f"  [{i+1}/{len(test_cases)}] {case.get('id', 'case')}: ", end="", flush=True)
        
        result = run_single_case(agent, case, config, include_rubrics)
        results.append(result)
        
        if verbose:
            status = "PASS" if result.passed else "FAIL"
            rubric = f" (rubric: {result.rubric_score:.1f})" if result.rubric_score else ""
            print(f"{status} ({result.latency_ms:.0f}ms){rubric}")
    
    # Aggregate metrics
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    total_input = sum(r.input_tokens for r in results)
    total_output = sum(r.output_tokens for r in results)
    
    rubric_scores = [r.rubric_score for r in results if r.rubric_score is not None]
    avg_rubric = sum(rubric_scores) / len(rubric_scores) if rubric_scores else 0
    
    return VariantResults(
        variant_name=variant_name,
        config=config,
        total_cases=len(results),
        passed=passed,
        failed=failed,
        pass_rate=passed / len(results) if results else 0,
        avg_rubric_score=avg_rubric,
        avg_latency_ms=sum(r.latency_ms for r in results) / len(results) if results else 0,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        estimated_cost=estimate_cost(total_input, total_output, config.get("model", "gpt-4o-mini")),
        results=results
    )


def run_experiment(
    variant_names: list[str],
    test_source: str = "golden",
    limit: Optional[int] = None,
    include_rubrics: bool = True,
    verbose: bool = True
) -> dict[str, VariantResults]:
    """Run experiment across multiple variants."""
    variants_path = Path(__file__).parent / "variants.yaml"
    all_variants = load_variants(str(variants_path))
    
    # Filter to requested variants
    if variant_names:
        variants = {k: v for k, v in all_variants.items() if k in variant_names}
    else:
        variants = all_variants
    
    # Load test cases
    test_cases = load_test_cases(test_source)
    if limit:
        test_cases = test_cases[:limit]
    
    if verbose:
        print(f"Running experiment with {len(variants)} variants")
        print(f"Test source: {test_source} ({len(test_cases)} cases)")
    
    results = {}
    for name, config in variants.items():
        results[name] = run_variant(
            name, config, test_cases,
            include_rubrics=include_rubrics,
            verbose=verbose
        )
    
    return results


def save_results(results: dict[str, VariantResults], output_dir: str):
    """Save experiment results to disk."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save summary
    summary = {
        "timestamp": timestamp,
        "variants": {}
    }
    
    for name, variant_result in results.items():
        summary["variants"][name] = {
            "pass_rate": variant_result.pass_rate,
            "avg_rubric_score": variant_result.avg_rubric_score,
            "avg_latency_ms": variant_result.avg_latency_ms,
            "estimated_cost": variant_result.estimated_cost,
            "total_cases": variant_result.total_cases,
            "passed": variant_result.passed,
            "failed": variant_result.failed
        }
        
        # Save detailed results
        detail_path = output_path / f"{name}_{timestamp}.json"
        with open(detail_path, "w") as f:
            json.dump({
                "variant": name,
                "config": variant_result.config,
                "results": [asdict(r) for r in variant_result.results]
            }, f, indent=2)
    
    summary_path = output_path / f"summary_{timestamp}.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    
    return summary_path


def print_comparison(results: dict[str, VariantResults]):
    """Print comparison table."""
    print("\n" + "=" * 70)
    print("EXPERIMENT RESULTS")
    print("=" * 70)
    
    # Header
    print(f"{'Variant':<15} {'Pass %':>8} {'Rubric':>8} {'Latency':>10} {'Cost':>10}")
    print("-" * 70)
    
    # Sort by pass rate
    sorted_results = sorted(results.items(), key=lambda x: -x[1].pass_rate)
    
    for name, r in sorted_results:
        print(f"{name:<15} {r.pass_rate*100:>7.0f}% {r.avg_rubric_score:>7.1f} {r.avg_latency_ms:>8.0f}ms ${r.estimated_cost:>8.4f}")
    
    print("=" * 70)
    
    # Winner
    winner = sorted_results[0]
    print(f"\nBest variant: {winner[0]} (pass rate: {winner[1].pass_rate*100:.0f}%)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run agent experiments")
    parser.add_argument("--variants", "-v",
                       help="Comma-separated variant names (default: all)")
    parser.add_argument("--test-source", "-t",
                       choices=["golden", "scenarios", "rubrics"],
                       default="golden",
                       help="Source of test cases")
    parser.add_argument("--limit", "-l", type=int,
                       help="Limit number of test cases per variant")
    parser.add_argument("--no-rubrics", action="store_true",
                       help="Skip rubric scoring (faster)")
    parser.add_argument("--output", "-o",
                       default="results",
                       help="Output directory for results")
    parser.add_argument("--quiet", "-q", action="store_true",
                       help="Minimal output")
    args = parser.parse_args()
    
    variant_names = args.variants.split(",") if args.variants else []
    
    results = run_experiment(
        variant_names=variant_names,
        test_source=args.test_source,
        limit=args.limit,
        include_rubrics=not args.no_rubrics,
        verbose=not args.quiet
    )
    
    # Save results
    output_dir = Path(__file__).parent / args.output
    summary_path = save_results(results, str(output_dir))
    print(f"\nResults saved to: {summary_path}")
    
    # Print comparison
    print_comparison(results)
