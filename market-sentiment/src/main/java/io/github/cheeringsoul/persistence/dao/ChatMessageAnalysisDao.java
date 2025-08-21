package io.github.cheeringsoul.persistence.dao;

import io.github.cheeringsoul.analyzer.pojo.ChatMessageAnalysisResult;
import org.jdbi.v3.sqlobject.config.RegisterBeanMapper;
import org.jdbi.v3.sqlobject.customizer.Bind;
import org.jdbi.v3.sqlobject.customizer.BindBean;
import org.jdbi.v3.sqlobject.statement.SqlQuery;
import org.jdbi.v3.sqlobject.statement.SqlUpdate;

@RegisterBeanMapper(ChatMessageAnalysisResult.class)
public interface ChatMessageAnalysisDao {

    @SqlUpdate("""
        INSERT INTO message_summary (message_count, start_time, end_time)
        VALUES (:messageCount, :startTime, :endTime)
        RETURNING id
    """)
    long insert(@BindBean ChatMessageAnalysisResult result);

    @SqlQuery("SELECT * FROM message_summary WHERE id = :id")
    ChatMessageAnalysisResult findById(@Bind("id") long id);
}