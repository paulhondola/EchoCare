package ro.echocare.home

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.launch
import ro.echocare.EchoCareApi
import ro.echocare.MockAnswer
import ro.echocare.MockCall
import ro.echocare.SeniorPage

/** One senior's page: GET /seniors/{id} (seniors §3.3). */
@HiltViewModel
class SeniorViewModel @Inject constructor(private val api: EchoCareApi) : ViewModel() {
    var page by mutableStateOf<Load<SeniorPage>>(Load.Loading)
        private set

    /** A weather warning is in force (Q17); read with the senior's own home only. */
    var warning by mutableStateOf(false)
        private set

    /** The call the card answers; null when none is due or on production (design §6.2). */
    var mock by mutableStateOf<MockCall?>(null)
        private set

    /** [id] is null on the senior's own home: the one senior their grant names. */
    fun reread(id: String?) {
        viewModelScope.launch {
            page = page.after(read(id))
            // A failed read keeps the last answer: the page's own banner says offline
            if (id == null) {
                (answer { api.me() } as? Answer.Ok)?.let { warning = it.value.warningActive }
                // A Response does not throw on a 5xx: only a definite answer changes the card
                val read = (answer { api.mockCall() } as? Answer.Ok)?.value
                mock = cardAfterRead(read?.code(), read?.body(), mock)
            }
        }
    }

    /**
     * Posts the card's answer. Once the server answered, even with a 409, the card goes and the
     * page rereads; a lost connection or a 5xx keeps the card to press again (design §6.2).
     */
    fun answer(body: MockAnswer) {
        val call = mock ?: return
        viewModelScope.launch {
            val sent = (answer { api.mockAnswer(call.callId, body) } as? Answer.Ok)?.value
            if (answerSettled(sent?.code())) {
                mock = null
                reread(null)
            }
        }
    }

    private suspend fun read(id: String?): Answer<SeniorPage> {
        val seniorId = id ?: when (val own = answer { api.seniors("senior") }) {
            is Answer.No -> return own
            is Answer.Ok -> own.value.firstOrNull()?.id ?: return Answer.No(Failure.NotFound)
        }
        return answer { api.senior(seniorId) }
    }
}
