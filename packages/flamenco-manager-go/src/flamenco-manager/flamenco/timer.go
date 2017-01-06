package flamenco

import (
	"log"
	"sync"
	"time"
)

type TimerPing struct{}

/**
 * Generic timer for periodic signals.
 *
 * :param sleep_first: if true: sleep first, then ping. If false: ping first, then sleep.
 */
func Timer(name string, sleep_duration time.Duration, sleep_first bool,
	done_chan <-chan bool, done_wg *sync.WaitGroup) <-chan TimerPing {
	timer_chan := make(chan TimerPing, 1) // don't let the timer block

	go func() {
		done_wg.Add(1)
		defer done_wg.Done()
		defer close(timer_chan)

		last_timer := time.Time{}
		if sleep_first {
			last_timer = time.Now()
		}

		for {
			select {
			case <-done_chan:
				log.Printf("Timer '%s' goroutine shutting down.\n", name)
				return
			default:
				// Only sleep a little bit, so that we can check 'done' quite often.
				time.Sleep(50 * time.Millisecond)
			}

			now := time.Now()
			if now.Sub(last_timer) > sleep_duration {
				// Timeout occurred
				last_timer = now
				timer_chan <- TimerPing{}
			}
		}
	}()

	return timer_chan
}
