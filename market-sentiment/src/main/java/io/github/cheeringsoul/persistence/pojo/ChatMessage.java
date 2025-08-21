package io.github.cheeringsoul.persistence.pojo;

import lombok.*;
import lombok.experimental.Accessors;
import org.jdbi.v3.core.mapper.reflect.ColumnName;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.List;

@Getter
@Setter
@ToString
public class ChatMessage extends Base {
    private long id;
    @Getter(AccessLevel.NONE)
    private Long messageId;
    private long chatId;
    private String groupName;
    private long senderId;
    private String messageText;
    private List<String> urls;
    @Getter(AccessLevel.NONE)
    private OffsetDateTime timestamp;

    @ColumnName("message_id")
    public Long messageId() {
        return messageId;
    }

    public Instant timestamp() {
        return timestamp.toInstant();
    }
}