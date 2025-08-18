package io.github.cheeringsoul.analyzer.pojo;

import lombok.Getter;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;

@Getter
public class ChatMessageBucket {
    private final List<SimpleChatMessage> messages = new ArrayList<>();

    public void addMessage(SimpleChatMessage message) {
        if (messages.isEmpty()) {
            messages.add(message);
        } else {
            var lastMessage = messages.getLast();
            if (Objects.equals(lastMessage.sender, message.sender)) {
                // merge with last message
                messages.set(messages.size() - 1, new SimpleChatMessage(message.sender, lastMessage.text + " " + message.text));
            } else {
                messages.add(message);
            }
        }
    }

    public Iterator<SimpleChatMessage> iterator() {
        return messages.iterator();
    }

    public boolean isEmpty() {
        return messages.isEmpty();
    }

    public void clear() {
        messages.clear();
    }
}
