package io.github.cheeringsoul.persistence.datasource;

import io.github.cheeringsoul.persistence.dao.MessageSummaryDao;
import io.github.cheeringsoul.persistence.pojo.MessageSummary;
import org.jdbi.v3.core.Jdbi;

import java.util.function.Supplier;

public class MessageSummaryDs implements DataSource<MessageSummary> {
    private final Jdbi jdbi;
    private MessageSummaryDao dao;

    public MessageSummaryDs(Supplier<Jdbi> jdbiSupplier) {
        this.jdbi = jdbiSupplier.get();
        this.dao = jdbi.onDemand(MessageSummaryDao.class);
    }

    @Override
    public void save(MessageSummary messageSummary) {
        dao.insert(messageSummary);
    }

    @Override
    public void close() {

    }
}
