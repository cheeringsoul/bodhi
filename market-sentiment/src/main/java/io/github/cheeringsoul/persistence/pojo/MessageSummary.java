package io.github.cheeringsoul.persistence.pojo;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;
import org.jdbi.v3.core.mapper.reflect.ColumnName;

import java.time.Instant;
import java.time.OffsetDateTime;

@Getter
@Setter
@ToString
public class MessageSummary extends Base {
    private long id;
    @ColumnName("chat_id")
    private long chatId;
    @ColumnName("message_count")
    private int messageCount;
    @ColumnName("start_time")
    private OffsetDateTime startTime;
    @ColumnName("end_time")
    private OffsetDateTime endTime;

    public Instant startTime() {
        return startTime.toInstant();
    }

    public Instant endTime() {
        return endTime.toInstant();
    }
}
