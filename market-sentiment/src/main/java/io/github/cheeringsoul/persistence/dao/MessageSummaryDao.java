package io.github.cheeringsoul.persistence.dao;

import io.github.cheeringsoul.persistence.pojo.MessageSummary;
import org.jdbi.v3.sqlobject.config.RegisterBeanMapper;
import org.jdbi.v3.sqlobject.customizer.BindBean;
import org.jdbi.v3.sqlobject.statement.SqlQuery;
import org.jdbi.v3.sqlobject.statement.SqlUpdate;

@RegisterBeanMapper(MessageSummary.class)
public interface MessageSummaryDao {
    @SqlUpdate("""
            INSERT INTO message_summary (chat_id, message_count, start_time, end_time)
            VALUES (:chatId, :messageCount, :startTime, :endTime)
            RETURNING id
            """)
    long insert(@BindBean MessageSummary entity);

    @SqlQuery("""
            SELECT * FROM message_summary
            WHERE chat_id = :chatId AND start_time >= to_timestamp(:timestamp)
            ORDER BY start_time ASC LIMIT :limit
            """)
    MessageSummary findAfterTimestamp(long chatId, long timestamp, int limit);

}
