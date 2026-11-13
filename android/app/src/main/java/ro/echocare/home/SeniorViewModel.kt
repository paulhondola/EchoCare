package ro.echocare.home

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import ro.echocare.CallRow
import ro.echocare.EchoCareApi
import ro.echocare.IncidentCall
import ro.echocare.MedicalItem
import ro.echocare.MedicalRecord
import ro.echocare.MockAnswer
import ro.echocare.MockCall
import ro.echocare.R
import ro.echocare.SeniorPage
import ro.echocare.enroll.Point
import ro.echocare.enroll.ensure
import ro.echocare.enroll.signatureForm

/** One senior's page: GET /seniors/{id} (seniors §3.3). */
@HiltViewModel
class SeniorViewModel @Inject constructor(
    private val api: EchoCareApi,
    @ApplicationContext private val context: Context
) : ViewModel() {
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

    /**
     * The medic's list read and this senior is not on it: someone she reaches by another grant,
     * such as a caregiver's, opened from an alert. Her page then shows no medic panel (UC-12).
     */
    var notHers by mutableStateOf(false)
        private set

    /** The medical record (design §5.7); null until read, and for anyone but the medic. */
    var medical by mutableStateOf<MedicalRecord?>(null)
        private set

    /** Set by the screen: the medic's panel is shown, so the record is read with the page. */
    var readsMedical = false

    /** A string resource: why the last upload did not go (design §5.7). */
    var uploadNotice by mutableStateOf<Int?>(null)
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
        val here = lastKnownLocation(context)
        val form = manualRequest().copy(
            latitude = here?.latitude,
            longitude = here?.longitude,
            locationAccuracyM = here?.accuracy?.toDouble()
        )
        viewModelScope.launch { callMe = callMeAfter(answer { api.sendEvent(form) }) }
    }

    /** [id] is null on the senior's own home: the one senior their grant names. */
    fun reread(id: String?) {
        // A read still under way is out of date; left running, it could land after this one
        reading?.cancel()
        reading = viewModelScope.launch {
            val read = read(id)
            page = page.after(read)
            if (read is Answer.Ok) {
                noteNumber(read.value)
                notice = noticeAfterRead(notice)
            }
            // A failed read keeps the last list, as the page keeps its last answer
            if (id != null) (answer { api.calls(id) } as? Answer.Ok)?.let { calls = it.value }
            if (id != null && readsMedical) {
                // A failed read keeps the last; a 204 is no record
                (answer { api.medicalRecord(id) } as? Answer.Ok)?.value?.let { r ->
                    if (r.isSuccessful) {
                        medical = r.body()
                    } else if (r.code() == 204) {
                        medical = null
                    }
                }
            }
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

    /** Sets [notHers] once the medic's list says [id] is not one of her patients. */
    fun checkHers(id: String) {
        viewModelScope.launch {
            (answer { api.seniors("medic") } as? Answer.Ok)?.let { rows ->
                notHers = rows.value.none { it.id == id }
            }
        }
    }

    /** „Editează datele”: remembers the number, to tell whether the form changed it. */
    fun editing() {
        (page as? Load.Ready)?.value?.let { phoneBeforeEdit = it.phone }
    }

    /**
     * „Sună din nou”: queues a welcome call to the number on file, at once (UC-04, 04 §2).
     * [onChanged] runs after an answer that may have moved the senior: a list beside the page
     * rereads, so the patient changes group at once (UC-12).
     */
    fun callAgain(id: String, onChanged: () -> Unit = {}) =
        runCommand(id, onChanged) { api.callAgain(id) }

    /** „Retrage”, after the dialog: the senior is called no more (04 §2). As [callAgain]. */
    fun withdraw(id: String, onChanged: () -> Unit = {}) =
        runCommand(id, onChanged) { api.withdraw(id) }

    /**
     * „Salvează semnătura”: posts the thinned strokes (G7, 04 §2). A failure shows its banner and
     * the pad keeps its drawing; as [callAgain] otherwise.
     */
    fun sign(
        id: String,
        strokes: List<List<Point>>,
        width: Float,
        height: Float,
        onChanged: () -> Unit = {}
    ) = runCommand(id, onChanged) { ensure(api.sign(id, signatureForm(strokes, width, height))) }

    /** Uploads the PDF; over the limit nothing is sent (design §5.7). */
    fun uploadPdf(id: String, bytes: ByteArray, onChanged: () -> Unit = {}) {
        if (bytes.size > MAX_PDF_BYTES) {
            uploadNotice = R.string.medical_too_large
            return
        }
        // The upload's own line replaces the generic banner
        runCommand(id, onChanged, failed = {
            notice = null
            uploadNotice = R.string.medical_upload_failed
        }) {
            api.uploadMedicalRecord(id, bytes.toRequestBody("application/pdf".toMediaType()))
        }
    }

    /** „Confirmă”: the medic's edits and choices, in the stored order (design §5.5). */
    fun confirmMedical(id: String, items: List<MedicalItem>) = runCommand(id, {}) {
        api.confirmMedicalRecord(
            id,
            confirmFormOf(
                items,
                medical?.items ?: items,
                medical?.analyzedAt
            )
        )
    }

    /** „Analizează din nou” (design §5.3). */
    fun reanalyzeMedical(id: String) = runCommand(id, {}) { api.reanalyzeMedicalRecord(id) }

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

    /**
     * One command at a time. Any answer but [CommandOutcome.Offline] rereads the senior and runs
     * [onChanged].
     */
    private fun runCommand(
        id: String,
        onChanged: () -> Unit,
        failed: () -> Unit = {},
        call: suspend () -> Any?
    ) {
        if (busy) return
        busy = true
        notice = null
        uploadNotice = null
        viewModelScope.launch {
            val outcome = command { call() }
            notice = outcome.takeIf { it != CommandOutcome.Done }
            if (outcome != CommandOutcome.Done) failed()
            if (outcome != CommandOutcome.Offline) {
                numberChanged = false
                reread(id)
                onChanged()
                // Busy until the page shows the answer: a second tap on the old page would
                // post a second signature or withdraw again
                reading?.join()
            }
            busy = false
        }
    }

    /** A number other than the one before the edit, on a senior to resolve, shows the banner. */
    private fun noteNumber(senior: SeniorPage) {
        phoneBeforeEdit?.let { before ->
            if (senior.phone != before) {
                numberChanged = isNewNumberToCall(before, senior)
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
