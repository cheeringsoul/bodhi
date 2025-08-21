package io.github.cheeringsoul.persistence.dao;

import io.github.cheeringsoul.analyzer.pojo.ChatMessageAnalysisResult;

import java.util.List;

public class DatabaseDataSource implements DataSource<ChatMessageAnalysisResult> {
    private final ChatMessageAnalysisDao dao;

    public DatabaseDataSource(ChatMessageAnalysisDao dao) {
        this.dao = dao;
    }

    @Override
    public List<ChatMessageAnalysisResult> read() {
        return List.of();
    }

    @Override
    public void close() {
        // 数据库连接池一般全局管理，这里可以不做事
    }
}
