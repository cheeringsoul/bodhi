package io.github.cheeringsoul.persistence.datasource;

import io.github.cheeringsoul.analyzer.pojo.ChatMessageAnalysisResult;
import io.github.cheeringsoul.persistence.dao.ChatMessageAnalysisDao;

import java.util.List;

public class ChatMessageAnalysisResultDs implements DataSource<ChatMessageAnalysisResult> {
    private final ChatMessageAnalysisDao dao;

    public ChatMessageAnalysisResultDs(ChatMessageAnalysisDao dao) {
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
