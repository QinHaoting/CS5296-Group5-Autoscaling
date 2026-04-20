package io.cs5296.consumer;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Message consumer that performs a CPU-bound computation for a configurable
 * duration. The busy-wait ensures HPA (which observes CPU) has a signal to
 * react to; without it HPA would never trigger and the comparison would be
 * meaningless.
 */
@Component
public class MessageConsumer {

    private static final Logger log = LoggerFactory.getLogger(MessageConsumer.class);

    @Value("${consumer.process-ms:200}")
    private long processMs;

    private final Counter processedCounter;
    private final Timer processingTimer;

    public MessageConsumer(MeterRegistry registry) {
        this.processedCounter = Counter.builder("consumer.messages.processed")
                .description("Total messages processed")
                .register(registry);
        this.processingTimer = Timer.builder("consumer.message.duration")
                .description("Time spent processing each message")
                .register(registry);
    }

    @RabbitListener(queues = "${consumer.queue}")
    public void handle(String payload) {
        processingTimer.record(() -> {
            busyWork(processMs);
            processedCounter.increment();
        });
        if (log.isDebugEnabled()) {
            log.debug("processed: {} chars", payload == null ? 0 : payload.length());
        }
    }

    /**
     * Deliberate CPU-bound busy wait. Using Thread.sleep would not consume CPU
     * and HPA would never see utilisation rise above the scale-up threshold.
     */
    private void busyWork(long millis) {
        long deadline = System.currentTimeMillis() + millis;
        double acc = 0.0;
        while (System.currentTimeMillis() < deadline) {
            acc += Math.sin(Math.random()) * Math.cos(Math.random());
        }
        if (Double.isNaN(acc)) {
            log.warn("acc became NaN");
        }
    }
}
