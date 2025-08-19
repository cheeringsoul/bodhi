package io.github.cheeringsoul.analyzer.impl;

import io.github.cheeringsoul.analyzer.Analyzer;
import io.github.cheeringsoul.analyzer.pojo.ChannelNewAnalysisResult;
import io.github.cheeringsoul.persistence.pojo.ChannelNews;

import java.util.Optional;

public class ChannelNewsAnalyzer implements Analyzer<ChannelNews, ChannelNewAnalysisResult> {

    @Override
    public Optional<ChannelNewAnalysisResult> analysis(ChannelNews data) {
        return Optional.empty();
    }
}
