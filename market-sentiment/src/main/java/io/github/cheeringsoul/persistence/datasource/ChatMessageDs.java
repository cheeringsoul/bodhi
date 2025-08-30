package io.github.cheeringsoul.persistence.datasource;

import io.github.cheeringsoul.persistence.dao.ChatMessageDao;
import io.github.cheeringsoul.persistence.pojo.ChatMessage;
import org.jdbi.v3.core.Jdbi;

import java.time.Instant;
import java.util.LinkedList;
import java.util.List;
import java.util.function.Supplier;

public class ChatMessageDs implements DataSource<ChatMessage> {
    private final Jdbi jdbi;

    private Instant start;
    private ChatMessageDao dao;
    private final List<ChatMessage> cached = new LinkedList<>();

    public ChatMessageDs(Supplier<Jdbi> jdbiSupplier) {
        this.jdbi = jdbiSupplier.get();
        this.dao = jdbi.onDemand(ChatMessageDao.class);
    }

    public ChatMessageDs(Supplier<Jdbi> jdbiSupplier, Instant start) {
        this.start = start;
        this.jdbi = jdbiSupplier.get();

    }

    @Override
    public ChatMessage read() {
        if (!cached.isEmpty()) {
            return cached.removeFirst();
        }
        if (start == null) {
            ChatMessage chatMessage = dao.findEarliest();
            start = chatMessage.timestamp();
        }

        List<ChatMessage> result = dao.findAfterTimestamp(start, 1000);
        if (result.isEmpty()) {
            return null;
        }
        start = result.getLast().timestamp();
        cached.addAll(result);
        return cached.removeFirst();
    }

    @Override
    public void close() {

    }
}
