package io.github.cheeringsoul.persistence.datasource;

import io.github.cheeringsoul.persistence.pojo.ChatMessage;

import java.util.List;

public class ChatMessageDs implements DataSource<ChatMessage> {
    @Override
    public List<ChatMessage> read() {
        return List.of();
    }

    @Override
    public void close() {

    }
}
