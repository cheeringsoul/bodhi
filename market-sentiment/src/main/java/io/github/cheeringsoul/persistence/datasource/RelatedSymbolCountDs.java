package io.github.cheeringsoul.persistence.datasource;

import io.github.cheeringsoul.persistence.dao.RelatedSymbolCountDao;
import io.github.cheeringsoul.persistence.pojo.RelatedSymbolCount;
import org.jdbi.v3.core.Jdbi;

import java.util.function.Supplier;

public class RelatedSymbolCountDs implements DataSource<RelatedSymbolCount, Long> {
    private final RelatedSymbolCountDao dao;

    public RelatedSymbolCountDs(Supplier<Jdbi> supplier) {
        this.dao = supplier.get().onDemand(RelatedSymbolCountDao.class);
    }

    @Override
    public Long save(RelatedSymbolCount entity) {
        return dao.insert(entity);
    }

}
