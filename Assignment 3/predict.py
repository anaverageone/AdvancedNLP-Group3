
from transformers import pipeline
from torch.nn import CrossEntropyLoss
from torch.utils.data import TensorDataset, DataLoader, SequentialSampler
from transformers import BertForTokenClassification, BertTokenizer
import logging
import bert_utils_srl as utils
import make_jsonl as jsonl

GPU_IX=0
device, USE_CUDA = utils.get_torch_device(GPU_IX)
FILE_HAS_GOLD = True
SEQ_MAX_LEN = 512
BATCH_SIZE = 4

MODEL_DIR = "saved_models/MY_BERT_NER/"
LOAD_EPOCH = 1
INPUTS_PATH=f"{MODEL_DIR}/EPOCH_{LOAD_EPOCH}/model_inputs.txt"
OUTPUTS_PATH=f"{MODEL_DIR}/EPOCH_{LOAD_EPOCH}/model_outputs.txt"
PAD_TOKEN_LABEL_ID = CrossEntropyLoss().ignore_index # -100

console_hdlr = logging.StreamHandler(sys.stdout)
file_hdlr = logging.FileHandler(filename=f"{MODEL_DIR}/EPOCH_{LOAD_EPOCH}/BERT_TokenClassifier_predictions.log")
logging.basicConfig(level=logging.INFO, handlers=[console_hdlr, file_hdlr])


def main():
    '''
    This function provides the following:
    - load the test set
    - pre-process original datasets into jsonl format
    - pre-process jsonl format datasets with BertTokenizer
    - datasets formatted to DataLoader matrices
    - load the fine-tuned model
    - predict labels for the test set
    - log all the progress
    - provide the precision, recall, and f1-score 
    
    '''
    
    # ------------------------------------------------------------------- #
    print("Read test dataset and convert to jsonl format")
    # ------------------------------------------------------------------- #
    test_jsonl_file = jsonl.main(['make_jsonl.py', False, True])

    ### ------ update testing data jsonl file ------ ###
    TEST_DATA_PATH = test_jsonl_file

    # ------------------------------------------------------------------- #
    print("Load the pretrained model from train.py")
    # ------------------------------------------------------------------- #

    model, tokenizer = utils.load_model(BertForTokenClassification, BertTokenizer, f"{MODEL_DIR}/EPOCH_{LOAD_EPOCH}")
    label2index = utils.load_label_dict(f"{MODEL_DIR}/label2index.json")
    index2label = {v:k for k,v in label2index.items()}


    # ------------------------------------------------------------------- #
    print("Test Dataset for prediction - load jsonl dev set, pre-process with tokenizer, create DataLoader")
    # ------------------------------------------------------------------- #
    train_pred2index = {'0':0, '1':1}
    
    test_data, test_labels, _, test_pred_sense, _ = utils.read_json_srl(TEST_DATA_PATH)
    prediction_inputs, prediction_masks, gold_labels, seq_lens, gold_pred = utils.data_to_tensors(test_data, 
                                                                                   tokenizer, 
                                                                                   max_len=SEQ_MAX_LEN, 
                                                                                   labels=test_labels, 
                                                                                   label2index=label2index,
                                                                                   pred2index=train_pred2index,
                                                                                   pred_sense=test_pred_sense)
    




    # ------------------------------------------------------------------- #
    print("Start prediction process")
    # ------------------------------------------------------------------- #
    if FILE_HAS_GOLD:
        prediction_data = TensorDataset(prediction_inputs, prediction_masks, gold_labels, gold_pred)
        prediction_sampler = SequentialSampler(prediction_data)
        prediction_dataloader = DataLoader(prediction_data, sampler=prediction_sampler, batch_size=BATCH_SIZE)

        logging.info('Predicting labels for {:,} test sentences...'.format(len(prediction_inputs)))
                                                                                                
        results, preds_list = utils.evaluate_bert_model(prediction_dataloader, BATCH_SIZE, model, tokenizer, index2label, 
                                                            PAD_TOKEN_LABEL_ID, full_report=True, prefix="Test Set")
        logging.info("  Test Loss: {0:.2f}".format(results['loss']))
        logging.info("  Precision: {0:.2f} || Recall: {1:.2f} || F1: {2:.2f}".format(results['precision']*100, results['recall']*100, results['f1']*100))

        with open(OUTPUTS_PATH, "w") as fout:
            with open(INPUTS_PATH, "w") as fin:
                for sent, pred in preds_list:
                    fin.write(" ".join(sent)+"\n")
                    fout.write(" ".join(pred)+"\n")

    else:
        # https://huggingface.co/transformers/main_classes/pipelines.html#transformers.TokenClassificationPipeline
        logging.info('Predicting labels for {:,} test sentences...'.format(len(test_data)))
        if not USE_CUDA: GPU_IX = -1
        nlp = pipeline('token-classification', model=model, tokenizer=tokenizer, device=GPU_IX)
        nlp.ignore_labels = []
        with open(OUTPUTS_PATH, "w") as fout:
            with open(INPUTS_PATH, "w") as fin:
                for seq_ix, seq in enumerate(test_data):
                    sentence = " ".join(seq)
                    predicted_labels = []
                    output_obj = nlp(sentence)
                    # [print(o) for o in output_obj]
                    for tok in output_obj:
                        if '##' not in tok['word']:
                            predicted_labels.append(tok['entity'])
                    logging.info(f"\n----- {seq_ix+1} -----\n{seq}\nPRED:{predicted_labels}")
                    fin.write(sentence+"\n")
                    fout.write(" ".join(predicted_labels)+"\n")


if __name__ == '__main__':
    main()