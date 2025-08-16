package io.github.cheeringsoul.analyzer;

import io.github.cheeringsoul.analyzer.pojo.internal.AnalysisResult;
import io.github.cheeringsoul.persistence.pojo.Base;

public interface AggregatedAnalyzer<T extends Base> {
    AnalysisResult aggregate(T data);
}
