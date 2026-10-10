package bia.sentinela

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import bia.sentinela.ui.theme.SentinelaTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            SentinelaTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    ApiStatus(modifier = Modifier.padding(innerPadding))
                }
            }
        }
    }
}

// Skeleton screen: shows whether FastAPI answers, like the dashboard skeleton.
@Composable
fun ApiStatus(modifier: Modifier = Modifier) {
    var text by remember { mutableStateOf("Checking API…") }
    LaunchedEffect(Unit) {
        text = runCatching { Api.sentinela.health() }
            .fold({ "API ${it.status} (${it.env})" }, { "API unreachable: ${it.message}" })
    }
    Text(text = text, modifier = modifier)
}

@Preview(showBackground = true)
@Composable
fun ApiStatusPreview() {
    SentinelaTheme {
        Text("API ok (local)")
    }
}
