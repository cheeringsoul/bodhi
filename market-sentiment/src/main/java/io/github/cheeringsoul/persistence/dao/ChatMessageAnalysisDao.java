package io.github.cheeringsoul.persistence.dao;

import io.github.cheeringsoul.analyzer.pojo.ChatMessageAnalysisResult;
import org.jdbi.v3.sqlobject.config.RegisterBeanMapper;
import org.jdbi.v3.sqlobject.customizer.Bind;
import org.jdbi.v3.sqlobject.customizer.BindBean;
import org.jdbi.v3.sqlobject.statement.SqlQuery;
import org.jdbi.v3.sqlobject.statement.SqlUpdate;

import java.time.Instant;
import java.util.List;

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


    @SqlQuery("""
                SELECT * FROM message_summary
                WHERE start_time >= :startTime AND end_time <= :endTime
                ORDER BY start_time ASC
            """)
    List<ChatMessageAnalysisResult> findByTimeRange(@Bind("startTime") Instant startTime,
                                                    @Bind("endTime") Instant endTime);
}