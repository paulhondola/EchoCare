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

    /** The call the card answers (design §6.2); null when none is due, on a 404 or a failed read. */
    var mock by mutableStateOf<MockCall?>(null)
        private set

    /** [id] is null on the senior's own home: the one senior their grant names. */
    fun reread(id: String?) {
        viewModelScope.launch {
            page = page.after(read(id))
            // A failed read keeps the last answer: the page's own banner says offline
            if (id == null) {
                (answer { api.me() } as? Answer.Ok)?.let { warning = it.value.warningActive }
                // A 204 has no body, a 404 means production, and a failed read shows no card
                mock = (answer { api.mockCall() } as? Answer.Ok)?.value?.body()
            }
        }
    }

    /** Posts the card's answer, then the card goes and the page rereads, a 409 included (design §6.2). */
    fun answer(body: MockAnswer) {
        val call = mock ?: return
        viewModelScope.launch {
            answer { api.mockAnswer(call.callId, body) }
            mock = null
            reread(null)
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
