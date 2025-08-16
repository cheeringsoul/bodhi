package io.github.cheeringsoul.analyzer;

import io.github.cheeringsoul.analyzer.pojo.AnalysisResult;
import io.github.cheeringsoul.persistence.pojo.Base;

import java.util.Optional;

public interface AggregatedAnalyzer<E extends Base, T extends AnalysisResult> {
    Optional<T> aggregate(E data);
}
