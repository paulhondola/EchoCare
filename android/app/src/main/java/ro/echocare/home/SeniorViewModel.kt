package ro.echocare.home

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import ro.echocare.CallRow
import ro.echocare.EchoCareApi
import ro.echocare.IncidentCall
import ro.echocare.MockAnswer
import ro.echocare.MockCall
import ro.echocare.SeniorPage

/** One senior's page: GET /seniors/{id} (seniors §3.3). */
@HiltViewModel
class SeniorViewModel @Inject constructor(private val api: EchoCareApi) : ViewModel() {
    var page by mutableStateOf<Load<SeniorPage>>(Load.Loading)
        private set

    /** A weather warning is in force (Q5); read with the senior's own home only. */
    var warning by mutableStateOf(false)
        private set

    /** The call the card answers; null when none is due or on production (design §6.2). */
    var mock by mutableStateOf<MockCall?>(null)
        private set

    /** The short call history (UC-12); null until read, and on the senior's own home. */
    var calls by mutableStateOf<List<CallRow>?>(null)
        private set

    /** What „Sunați-mă” shows (UC-10). */
    var callMe by mutableStateOf(CallMe.Idle)
        private set

    /** A command in flight: „Sună din nou” and „Retrage” wait for it (UC-12). */
    var busy by mutableStateOf(false)
        private set

    /** The banner after a command that did not go through; null after one that did. */
    var notice by mutableStateOf<CommandOutcome?>(null)
        private set

    /** The form saved a new number for a senior to resolve: „Sună din nou” calls it (04 §2). */
    var numberChanged by mutableStateOf(false)
        private set

    /** Each call's transcript the medic opened, by call id, read once (04 §1). */
    var transcripts by mutableStateOf<Map<String, Load<IncidentCall>>>(emptyMap())
        private set

    private var reading: Job? = null

    /** The number on the page when „Editează datele” was pressed, until a reread shows another. */
    private var phoneBeforeEdit: String? = null

    /**
     * „Sunați-mă”. No retry: a failed tap shows [CallMe.NotSent] and the senior taps again, with a
     * new id. A signed-out session ends on the next reread.
     */
    fun requestCall() {
        if (callMe == CallMe.Sending) return
        callMe = CallMe.Sending
        viewModelScope.launch { callMe = callMeAfter(answer { api.sendEvent(manualRequest()) }) }
    }

    /** [id] is null on the senior's own home: the one senior their grant names. */
    fun reread(id: String?) {
        // A read still under way is out of date; left running, it could land after this one
        reading?.cancel()
        reading = viewModelScope.launch {
            val read = read(id)
            page = page.after(read)
            if (read is Answer.Ok) noteNumber(read.value)
            // A failed read keeps the last list, as the page keeps its last answer
            if (id != null) (answer { api.calls(id) } as? Answer.Ok)?.let { calls = it.value }
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

    /** „Editează datele”: remembers the number, to tell whether the form changed it. */
    fun editing() {
        (page as? Load.Ready)?.value?.let { phoneBeforeEdit = it.phone }
    }

    /** „Sună din nou”: queues a welcome call to the number on file, at once (UC-04, 04 §2). */
    fun callAgain(id: String) = runCommand(id) { api.callAgain(id) }

    /** „Retrage”, after the dialog: the senior is called no more (04 §2). */
    fun withdraw(id: String) = runCommand(id) { api.withdraw(id) }

    /** „Transcriere”: reads the call's transcript once; a failed read is tried again on a tap. */
    fun openTranscript(callId: String) {
        val known = transcripts[callId]
        if (known is Load.Ready || known == Load.Loading) return
        transcripts = transcripts + (callId to Load.Loading)
        viewModelScope.launch {
            val read = answer { api.transcript(callId) }
            transcripts = transcripts + (callId to Load.Loading.after(read))
        }
    }

    /** One command at a time. Any answer but [CommandOutcome.Offline] rereads the senior. */
    private fun runCommand(id: String, call: suspend () -> Unit) {
        if (busy) return
        busy = true
        notice = null
        viewModelScope.launch {
            val outcome = command(call)
            notice = outcome.takeIf { it != CommandOutcome.Done }
            if (outcome != CommandOutcome.Offline) {
                numberChanged = false
                reread(id)
            }
            busy = false
        }
    }

    /** A number other than the one before the edit, on a senior to resolve, shows the banner. */
    private fun noteNumber(senior: SeniorPage) {
        phoneBeforeEdit?.let { before ->
            if (senior.phone != before) {
                numberChanged = ro.echocare.home.numberChanged(before, senior)
                phoneBeforeEdit = null
            }
        }
        // „Sună din nou” or the scheduler moved them on: the hint no longer applies
        if (senior.state != "wrong_number" && senior.state != "unreachable") numberChanged = false
    }

    private suspend fun read(id: String?): Answer<SeniorPage> {
        val seniorId = id ?: when (val own = answer { api.seniors("senior") }) {
            is Answer.No -> return own
            is Answer.Ok -> own.value.firstOrNull()?.id ?: return Answer.No(Failure.NotFound)
        }
        return answer { api.senior(seniorId) }
    }
}
