package io.github.cheeringsoul.analyzer.pojo;

import org.apache.commons.lang3.tuple.Pair;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ChatMessageContainer {
    private final List<Pair<Long, String>> messages = new ArrayList<>();

    public void addMessage(Long senderId, String text) {
        if (messages.isEmpty()) {
            messages.add(Pair.of(senderId, text));
        } else {
            var lastMessage = messages.getLast();
            if (Objects.equals(lastMessage.getLeft(), senderId)) {
                // merge with last message
                messages.set(messages.size() - 1, Pair.of(senderId, lastMessage.getRight() + " " + text));
            } else {
                messages.add(Pair.of(senderId, text));
            }
        }
    }

    public List<Pair<Long, String>> getMessages() {
        return messages;
    }

    public void clear() {
        messages.clear();
    }
}
